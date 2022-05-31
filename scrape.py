#!/usr/bin/env python3
# coding: utf-8


import requests
from bs4 import BeautifulSoup
from urllib.parse import urlencode
from collections import OrderedDict
import re
import numpy as np
from datetime import datetime, timedelta
import rapidjson
import random
import sys
import time

# Set up logging to both stout and to a file
import logging, logging.handlers
logger = logging.getLogger("")
logger.setLevel(logging.INFO)
file_handler = logging.handlers.RotatingFileHandler("scraper.log", maxBytes=(1048576*5))
sterr_handler = logging.StreamHandler(sys.stderr)
# formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
# handler.setFormatter(formatter)
logger.addHandler(file_handler)
logger.addHandler(sterr_handler)
logger.critical("Starting...")

def get_properties_by_id(ids):
    "Access an unoficial API to get property data by id"
    assert len(ids) < 20 # API limit
    endpoint = "https://www.openrent.co.uk/search/propertiesbyid?"
    return requests.get(endpoint, [('ids', i) for i in ids]).json()

def make_link(property_id):
    "Construct a human usable link the a property"
    return f"https://www.openrent.co.uk/{property_id}"

def parse_js_list(s): 
    "Parse the list from a js var name = [...] statement that might have line breaks etc"
    return rapidjson.loads(s.replace('\n', '').replace("'", '"'), parse_mode = rapidjson.PM_TRAILING_COMMAS | rapidjson.PM_COMMENTS)

def our_filter(prop):
    if prop['availableFrom'] < start_date: return False
    if prop['isstudio']: return False
    if prop['isshared']: return False
    
    price = prop['prices']
    if price < 1500 or price > 2200: return False

    return True

# Load the config with a json parser that allows trailing commas
with open('config.json') as f: 
    config = rapidjson.load(f, parse_mode = rapidjson.PM_TRAILING_COMMAS | rapidjson.PM_COMMENTS)

#pull in config data
urls = config["search_urls"]
start_date = datetime.fromisoformat(config["start_date"])
slack_token = config["slack_token"]

# get our local list of properties we've already seen
with open('check_property_ids.txt', 'r') as f:
    checked_property_ids = set(int(i) for i in f.read().split('\n') if i != '')

all_properties = {}

for i, (search_name, search_url) in enumerate(urls.items()):
    r = requests.get(search_url)
    soup = BeautifulSoup(r.text, 'html.parser')

    # find the script tag that contains the data we want
    # the criteria I'm using is that it has a line that read "var PROPERTYIDS =  ..."
    # This is how we avoid having to scroll the page to get all the properties
    script_content = soup.find(lambda tag:tag.name=="script" and "PROPERTYIDS" in tag.text).text

    #pull out all the var name = [...] lines from the script using a regex
    variable_data_pairs = re.findall(r"var\s(\S+)\s?=\s?(\[[^\]]*\])", script_content)

    #parse that into a dictionary
    properties_arrays = {name : np.array(parse_js_list(data)) for name, data in variable_data_pairs}

    # Add the data parsed from the script to a properties[property_id] = {key : data about property} object
    ids = properties_arrays['PROPERTYIDS']
    logger.info(f"Search {search_name} returned {len(ids)} results")

    logger.debug(f"Parsing the results")
    properties = {}
    for i, id_ in enumerate(ids):
        prop = {name : data[i] for name, data in properties_arrays.items()}
        prop['availableFrom'] = datetime.today() + timedelta(days = int(prop['availableFrom']))
        properties[id_] = prop

    # Filter the results
    properties = {i : prop for i, prop in properties.items() if our_filter(prop)}
    logger.info(f"{len(properties)} of the results match our criteria.")

    # Filter out results we've already seen
    properties = {i : prop for i, prop in properties.items() if prop['PROPERTYIDS'] not in checked_property_ids}
    logger.info(f"{len(properties)} of those are new to us.")

    #iterate over the properties and grab random numbers of them 
    logger.debug(f"Pulling more data about the results from the openrent API")
    i = 0
    maxsize = 14 #maximum number of results to pull at once
    ids = list(properties.keys())
    while i < len(properties) - 1:
        N = random.randint(5, maxsize)
        if len(properties) < i + maxsize: N = len(properties) - i
        data = get_properties_by_id(ids[i : i + N])
        for d in data:
            properties[d['id']].update(d)
        i += N

    all_properties.update(properties)
    
logger.info(f"Overall we found {len(all_properties)} new properties.")
if len(all_properties) == 0: sys.exit()



from slack_sdk import WebClient
sc = WebClient(token = "xoxb-3616343189840-3592561774387-mK9AWd5bIi6KUgaps2RdGm3u")


def property_description(p):
    return {
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": f"""
£{p['prices']} {'incl bills' if p['bills'] else ''}| {p['bedrooms']} bed | Start {p['availableFrom'].strftime('%w %b %y')} {'| UNFURNISHED!' if p['unfurnished'] else ''}
<{make_link(p['id'])}|{p['title']}>
{p['description']}
            """,
            },

        "accessory" : {
              "type": "image",
              "image_url": 'http:' + p['imageUrl'],
              "alt_text": "Image of the flat"
        },
    }  
    
DIVIDER_BLOCK = {"type": "divider"}

header = {
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": (
            f"Found {len(all_properties)} new properties!"
        ),
    },
}

sc.chat_postMessage(
    channel = 'openrent',
    text = '{len(all_properties)} new properties found!',
    blocks = [header,])

for id_, prop in all_properties.items():
    sc.chat_postMessage(
        channel = 'openrent',
        text = 'New property found!',
        blocks = [property_description(prop),])
    time.sleep(0.1)

# update the list of known properties
with open('check_property_ids.txt', 'w') as f:
    updated = checked_property_ids | set(all_properties.keys())
    f.write("\n".join(str(i) for i in updated))



