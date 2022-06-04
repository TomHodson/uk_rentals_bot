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
from slack_sdk import WebClient
from itertools import islice
from random import randint

# Set up logging to both stout and to a file
import logging, logging.handlers
logger = logging.getLogger("")
logger.setLevel(logging.INFO)
# logger.setLevel(logging.DEBUG)
file_handler = logging.handlers.RotatingFileHandler("scraper.log", maxBytes=(1048576*5))
sterr_handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
for handler in [file_handler, sterr_handler]:
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.critical("Starting...")

def random_chunk(li, min_chunk=5, max_chunk=20):
    "split a list into randomly sized chunks"
    it = iter(li)
    while True:
        nxt = list(islice(it,randint(min_chunk,max_chunk)))
        if nxt:
            yield nxt
        else:
            break

def fmt_hours(n):
    if n < 24: return f"{n} hours"
    if n < 24 * 7: return f"{n/24:.0f} days"
    if n < 24 * 7 * 4: return f"{n/24/7:.0f} weeks"
    if n < 24 * 7 * 4 * 12: return f"{n/24/7/4:.0f} months"
    return f"{n/24/7/4/12:.0f} years"

def get_properties_by_id(ids, session = None):
    "Access an unoficial API to get property data by id"
    s = session if session else requests
    assert len(ids) < 20 # API limit
    endpoint = "https://www.openrent.co.uk/search/propertiesbyid?"
    return s.get(endpoint, params = [('ids', i) for i in ids]).json()

def make_link(property_id):
    "Construct a human usable link the a property"
    return f"https://www.openrent.co.uk/{property_id}"

def parse_js_list(s): 
    "Parse the list from a js var name = [...] statement that might have line breaks etc"
    return rapidjson.loads(s.replace('\n', '').replace("'", '"'), parse_mode = rapidjson.PM_TRAILING_COMMAS | rapidjson.PM_COMMENTS)

def our_filter(prop, start_date):
    if prop['availableFrom'] < start_date: return False
    if prop['isstudio']: return False
    if prop['isshared']: return False
    if not prop['islivelistBool']: return False
    if not prop['nonStudents']: return False
    # if prop['bedrooms'] < 2: return False

    
    price = prop['prices']
    if price < 1500 or price > 2200: return False

    return True

def load_config():
    "Load the config with a json parser that allows trailing commas"
    with open('config.json') as f: 
        config = rapidjson.load(f, parse_mode = rapidjson.PM_TRAILING_COMMAS | rapidjson.PM_COMMENTS)
    return config

def load_seen_properties(fname = 'check_property_ids.txt'):
    # get our local list of properties we've already seen
    with open(fname, 'r') as f:
        checked_property_ids = set(int(i) for i in f.read().split('\n') if i != '')
    return checked_property_ids

def search_properties(config, filter = None, already_seen = None):
    "Return properties from search urls in config, with optional filter function and already_seen set"
    urls = config["search_urls"]
    start_date = datetime.fromisoformat(config["start_date"])
    all_properties = {}

    with requests.session() as s:
        for i, (search_name, search_url) in enumerate(urls.items()):
            r = s.get(search_url)
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
            properties = {i : prop for i, prop in properties.items() if our_filter(prop, start_date)}
            logger.info(f"{len(properties)} of the results match our criteria.")

            # Filter out results we've already seen
            properties = {i : prop for i, prop in properties.items() if prop['PROPERTYIDS'] not in already_seen}
            logger.info(f"{len(properties)} of those are new to us.")

            #iterate over the properties and grab random numbers of them 
            logger.debug(f"Pulling more data about the results from the openrent API")
            for chunk in random_chunk(properties.keys()):
                data = get_properties_by_id(chunk, session = s)
                for d in data: properties[d['id']].update(d)

            all_properties.update(properties)
    return all_properties


#pull in config data
config = load_config()
already_seen_ids = load_seen_properties()
all_properties = search_properties(config, filter = our_filter, already_seen = already_seen_ids)
logger.info(f"Overall we found {len(all_properties)} new properties.")
if len(all_properties) == 0: sys.exit()

slack_token = config["slack_token"]
sc = WebClient(token = slack_token)

def property_description(id_, p):
    return {
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": f"""
£{p['prices']} {'incl bills' if p['bills'] else ''}| {p['bedrooms']} bed | Start {p['availableFrom'].strftime('%d %b %y')} {'| UNFURNISHED!' if p['unfurnished'] else ''}
<{make_link(id_)}|{p['title']}>
Online {fmt_hours(p['hoursLive'])}.
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
logger.debug(f"Properties: {all_properties}")

for id_, prop in all_properties.items():
    sc.chat_postMessage(
        channel = 'openrent',
        text = 'New property found!',
        blocks = [property_description(id_, prop),])
    time.sleep(0.1)

# update the list of known properties
with open('check_property_ids.txt', 'a') as f:
    f.write("\n".join(str(i) for i in all_properties.keys()) + "\n")



