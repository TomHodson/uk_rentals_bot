from bs4 import BeautifulSoup
import re
import numpy as np
import rapidjson
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
import requests
from collections import Counter

import logging, logging.handlers
logger = logging.getLogger("")
logger.setLevel(logging.INFO)

from utils import Property, random_chunk, pairs

openrent_keymap = {
    "PROPERTYIDS" : "id",
    # "title" : "title",
    # "description" : "description",
    # "letAgreed" : "letAgreed",
    "minimumTenancy" : "minimumTenancy",
    "availableFrom" : "availableFrom",
    "isstudio" : "isStudio",
    "isshared" : "isShared",
    "nonStudents" : "acceptsProfessionals",
    "bedrooms" : "bedrooms",
    "bathrooms" : "bathrooms",
    "gardens" : "hasGarden",
    "prices" : "price",
    "bills" : "includesBills",
    "islivelistBool" : "isLive",
    "furnished" : "isFurnished",
    "PROPERTYLISTLATITUDES" : "latitude",
    "PROPERTYLISTLONGITUDES" : "longitude",
}


def parse_js_list(s): 
    "Parse the list from a js var name = [...] statement that might have line breaks etc"
    return rapidjson.loads(s.replace('\n', '').replace("'", '"'), parse_mode = rapidjson.PM_TRAILING_COMMAS | rapidjson.PM_COMMENTS)

def get_properties_by_id(ids, session = None):
    "Access an unoficial API to get property data by id"
    s = session if session else requests
    assert len(ids) < 20 # API limit
    endpoint = "https://www.openrent.co.uk/search/propertiesbyid?"
    json = s.get(endpoint, params = [('ids', i.split(":")[1]) for i in ids]).json()
    return json

def make_link(property_id):
    "Construct a human usable link the a property"
    return f"https://www.openrent.co.uk/{property_id}"

@dataclass
class OpenRentSearch:
    name: str
    url: str
    properties: dict = field(default_factory = dict)
    
    def make_request(self, session = None):
        if session is None: session = requests
        r = session.get(self.url)
        soup = BeautifulSoup(r.text, 'html.parser')

        # find the script tag that contains the data we want
        # the criteria I'm using is that it has a line that read "var PROPERTYIDS =  ..."
        # This is how we avoid having to scroll the page to get all the properties
        script_content = soup.find(lambda tag:tag.name=="script" and "PROPERTYIDS" in tag.text).text

        #pull out all the var name = [...] lines from the script using a regex
        variable_data_pairs = re.findall(r"var\s(\S+)\s?=\s?(\[[^\]]*\])", script_content)

        #parse that into a dictionary
        properties_arrays = {openrent_keymap.get(key, key) : np.array(parse_js_list(data)) for key, data in variable_data_pairs}

        # Add the data parsed from the script to a properties[property_id] = {key : data about property} object
        ids = properties_arrays['id']
        logger.info(f"Search {self.name} returned {len(ids)} results")

        logger.debug(f"Parsing the results")
        properties = {}
        for i, id_ in enumerate(ids):
            prop = Property(**{name : data[i] for name, data in properties_arrays.items() if name in openrent_keymap.values()})
            prop.rawData = {name : data[i] for name, data in properties_arrays.items()}
            prop.availableFrom = datetime.now(timezone.utc) + timedelta(days = int(prop.availableFrom))
            prop.listedAt = datetime.now(timezone.utc) - timedelta(hours = int(properties_arrays['hoursLive'][i]))
            prop.url = make_link(prop.id)
            prop.id = f"openrent:{prop.id}"
            prop.agent = "openrent"
            properties[prop.id] = prop

        self.properties = properties
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

        self.properties = {k : v for k,v in self.properties.items() if filter_func(v)}
        return self

    def more_info(self, session = None):
        "Use an undocumented openrent api to get extra details about the properties"
        # iterate over the properties and grab random numbers of them 
        logger.debug(f"Pulling more data about the results from the openrent API")
        if session is None: session = requests
        for chunk in random_chunk(self.properties.keys()):
            data = get_properties_by_id(chunk, session = session)
            for d in data: 
                p = self.properties[f"openrent:{d['id']}"]
                p.rawData.update(d)
                p.title = d["title"]
                p.description = d["description"]
                p.letAgreed = d["letAgreed"]
                p.imgUrl = 'http:' + d['imageUrl']
    
    def even_more_info(self, session = None):
        for id, p in self.properties.items():
            r = requests.get(p.url)
            soup = BeautifulSoup(r.content, 'html.parser')

            try:
                stats_table_cells = soup.select('table.intro-stats td')
                extra_data = dict(pairs((c.text.strip().replace(":", "") for c in stats_table_cells)))
                p.maximumTenants = int(extra_data["Maximum Tenants"])
            except Exception as e:
                logger.warn(f"Err'd while trying to get maximum tenants: {e}")


    

