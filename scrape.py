#!/usr/bin/env python3
# coding: utf-8

import requests
from urllib.parse import urlparse
import dateutil.parser
from datetime import datetime, timezone
import rapidjson
import sys
import time
from slack_sdk import WebClient

from openrent import OpenRentSearch
from rightmove import RightmoveSearch
from utils import fmt_timedelta

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

def our_filter(prop, config):
    if prop.availableFrom != None and prop.availableFrom < config["start_date"]: return False
    if prop.isStudio == True: return False
    if prop.isShared == True: return False
    if prop.isLive == False: return False
    if prop.letAgreed == True: return False

    if prop.acceptsProfessionals == False: return False
    if prop.agent == "OpenRent": return False #use lowercase openrent for our own searches on openrent

    if prop.maximumTenants == 1: 
        return False
    
    elif prop.maximumTenants == 2:
        if prop.size and prop.size < 50: return False #too small
        if (prop.includesBills in [None, False]) and prop.price > 1800: return False
        if (prop.includesBills == True) and prop.price > 2200: return False
        prop.slack_channel = "two-people"
    
    elif prop.maximumTenants and prop.maximumTenants > 2:
        if prop.size and prop.size < 70: return False #too small
        if prop.bedrooms < 2: return False
        if (prop.includesBills in [None, False]) and prop.price > 2350: return False
        if (prop.includesBills == True) and prop.price > 2650: return False

    else: # prop.maximumTenants == None or 0 or something else weird
        if prop.size and prop.size < 50: return False # too small
        if (prop.includesBills in [None, False]) and prop.price > 2350: return False
        if (prop.includesBills == True) and prop.price > 2650: return False

    return True

def load_config():
    "Load the config with a json parser that allows trailing commas"
    with open('config.json') as f: 
        config = rapidjson.load(f, parse_mode = rapidjson.PM_TRAILING_COMMAS | rapidjson.PM_COMMENTS)
    return config

def load_seen_properties(fname = 'check_property_ids.txt'):
    # get our local list of properties we've already seen
    with open(fname, 'r') as f:
        checked_property_ids = set(i for i in f.read().split('\n') if i != '')
    return checked_property_ids

def search_properties(config, filter = None, already_seen = None):
    "Return properties from search urls in config, with optional filter function and already_seen set"
    urls = config["search_urls"]
    config["start_date"] = dateutil.parser.parse(config["start_date"], default = datetime.now(timezone.utc))
    all_properties = {}
    checked = set()

    with requests.session() as s:
        for i, (search_name, search_url) in enumerate(urls.items()):
            netloc = urlparse(search_url).netloc

            if netloc.endswith("openrent.co.uk"):
                search = OpenRentSearch(search_name, search_url)
            elif netloc.endswith("rightmove.co.uk"):
                search = RightmoveSearch(search_name, search_url)
            else:
                logger.warn(f"Don't (yet) know how to scrape {netloc}.")

            # do the search
            search.make_request(s)
            
            # Filter the results based on criteria
            search.filter(lambda p : our_filter(p, config))
            logger.info(f"{len(search.properties)} of the results match our criteria.")

            # Ignore anything we've already seen
            search.filter(lambda p : p.id not in already_seen)
            logger.info(f"{len(search.properties)} of those are new to us.")

            # Grab any extra info that requires making per property requests
            # Do this after filtering out the obvious ones you don't want
            search.more_info(s) 

            # Do an extra filter pass in case this extra info means that we now don't pass the test
            search.filter(lambda p : our_filter(p, config))
            logger.info(f"{len(search.properties)} of the results match our criteria after getting extra info.")

            all_properties.update(search.properties)
        
    return all_properties


#pull in config data
config = load_config()
already_seen_ids = load_seen_properties()
all_properties = search_properties(config, filter = our_filter, already_seen = already_seen_ids)
hostname = config["hostname"] or "dev_environment"
logger.info(f"Overall we found {len(all_properties)} new properties.")
# if len(all_properties) == 0: sys.exit()

slack_token = config["slack_token"]
sc = WebClient(token = slack_token)

def floorplan(url):
    return {
			"type": "image",
			"title": {
				"type": "plain_text",
				"text": "Floorplan",
				"emoji": True
			},
			"image_url": url,
			"alt_text": "Floor Plan"
		}

def property_description(p):
    return {
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": f"""
<{p.url}|{p.title}>
£{p.price} {'incl bills' if p.includesBills else ''}| {p.bedrooms} bed | Start {p.availableFrom.strftime('%d %b %y') if p.availableFrom else "?"} {'| UNFURNISHED!' if p.isFurnished == False else ''} {f'| {p.size} sq m' if p.size else ''}
On {p.agent} for {fmt_timedelta(p.listedAt)}.
Max Tenants: {p.maximumTenants or '?'}
{f"Nearest Station: {p.nearestStation}" if p.nearestStation else ""}
{p.description}
            """,
            },

        "accessory" : {
              "type": "image",
              "image_url": p.imgUrl,
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

#post a message that the bot ran to a differnt channel
sc.chat_postMessage(
    channel = config.get("debug_slack_channel") or "bot_testing",
    text = f"Ran at {datetime.now().strftime('%d %b %y %H:%M')} on {hostname}, found {len(all_properties)} new properties",
)

logger.debug(f"Properties: {all_properties}")
for id_, prop in all_properties.items():
    blocks = [property_description(prop),]
    # if prop.floorPlanUrl: blocks.append(floorplan(prop.floorPlanUrl))

    sc.chat_postMessage(
        channel = prop.slack_channel or config.get("slack_channel") or "openrent",
        text = 'New property found!',
        blocks = blocks,
    )
    time.sleep(0.1)

# update the list of known properties
with open('check_property_ids.txt', 'a') as f:
    if len(all_properties.keys()) > 0:
        f.write("\n" + "\n".join(str(i) for i in all_properties.keys()))



