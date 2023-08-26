from bs4 import BeautifulSoup
import re
import numpy as np
import rapidjson
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
import requests
import dateutil.parser
from collections import Counter

import logging, logging.handlers
logger = logging.getLogger("")
logger.setLevel(logging.INFO)

from utils import Property, random_chunk

rightmove_keymap = {
    "id" : "id",
    "bedrooms" : "bedrooms",
    "bathrooms" : "bathrooms",
    "summary" : "description",
    'propertyTypeFullDescription' : "title",
}

def format_rightmove_properties(raw):
    assert(raw["price"]['currencyCode'] == 'GBP')
    
    data = {rightmove_keymap.get(k) : v for k,v in raw.items() if k in rightmove_keymap}
    out = Property(**data)
    out.rawData = raw

    out.imgUrl = raw["propertyImages"]['mainImageSrc']
    out.id = f"rightmove:{raw['id']}"
    out.listedAt = dateutil.parser.isoparse(raw['firstVisibleDate'])
    out.latitude = raw["location"]['latitude']
    out.longitude = raw["location"]['longitude']
    out.agent = raw["customer"]['brandTradingName']
    out.availableFrom = None
    out.url = "https://rightmove.co.uk" + raw['propertyUrl']


    if raw["price"]['frequency'] == "monthly":
        out.price = raw["price"]["amount"]
    if raw["price"]['frequency'] == "weekly":
        out.price = raw["price"]["amount"] * 52 // 12
    assert(out.price != None)
    

    return out


@dataclass
class RightmoveSearch:
    name: str
    url: str
    properties: dict = field(default_factory = dict)
    
    def make_request(self, session = None):
        if session is None: session = requests
        r = session.get(self.url)
        soup = BeautifulSoup(r.text, 'html.parser')

        # find the script tag that contains the data we want
        script_content = soup.find(lambda tag:tag.name=="script" and "window.jsonModel = " in tag.text).text

        #pull out all the var name = [...] lines from the script using a regex
        json = re.match(r"window.jsonModel = (.*)", script_content).group(1)

        data = rapidjson.loads(json, parse_mode = rapidjson.PM_TRAILING_COMMAS | rapidjson.PM_COMMENTS)

        #parse that into a dictionary
        self.properties = {f"rightmove:{p['id']}" : format_rightmove_properties(p) for p in data["properties"]}

        logger.info(f"Search {self.name} returned {len(self.properties)} results")
        return self

    def filter(self, filter_func):
        filtered_properties = {}
        reasons = Counter()
        for k, v in self.properties.items():
            keep, reason = filter_func(v)
            reasons[reason] += 1
            if keep: filtered_properties[k] = v
        self.properties = filtered_properties
        return reasons

    def more_info(self, session = None):
        "Use an undocumented openrent api to get extra details about the properties"
        # iterate over the properties and grab random numbers of them 
        logger.debug(f"Pulling more data about the results from the openrent API")
        if session is None: session = requests
        for id, p in self.properties.items():
            r = session.get(p.url)
            soup = BeautifulSoup(r.text, 'html.parser')

            # find the script tag that contains the data we want
            script_content = soup.find(lambda tag:tag.name=="script" and "window.PAGE_MODEL = " in tag.text).text
            #pull out all the var name = [...] lines from the script using a regex
            json = re.match(r"[\s]*window.PAGE_MODEL = (.*)", script_content).group(1)
            data = rapidjson.loads(json, parse_mode = rapidjson.PM_TRAILING_COMMAS | rapidjson.PM_COMMENTS)
            data = data['propertyData']
            # print(data)

            try: p.title = data["address"]["displayAddress"]
            except KeyError: pass

            try: p.floorPlanUrl = data["floorplans"][0]["url"]
            except (KeyError, IndexError): pass

            try: p.contactTelephone = data['contactInfo']['telephoneNumbers']['localNumber']
            except KeyError: pass
            
            try: p.isFurnished = data['lettings']['furnishType'] == 'Furnished'
            except KeyError: pass

            try: 
                sizes = {d["unit"] : d["minimumSize"] for d in data["sizings"]}
                p.size = sizes["sqm"]
            except KeyError: pass

            try: 
                date_str = data['lettings']['letAvailableDate']
                now = datetime.now(timezone.utc)
                if date_str: 
                    if "now" in date_str.lower(): p.availableFrom = now
                    else: p.availableFrom = dateutil.parser.parse(data['lettings']['letAvailableDate'], default = now, dayfirst = True)
            except KeyError: pass
            except dateutil.parser._parser.ParserError as e: logger.warn(e)

            try:
                if data['keyFeatures']:
                    p.description = "Key Features: " + ", ".join(data['keyFeatures'])
                else: p.description = ""
            except KeyError: pass

            try:
                p.nearestStation = data["nearestStations"][0]["name"]
            except (KeyError, IndexError): pass
