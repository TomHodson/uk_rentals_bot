#!/usr/bin/env python3
# coding: utf-8

import requests
from urllib.parse import urlparse
import dateutil.parser
from datetime import datetime, timezone
import yaml
import sys
import time
import re
from slack_sdk import WebClient
from pathlib import Path
from typing import Optional

from dataclasses import dataclass, field

from openrent import OpenRentSearch
from rightmove import RightmoveSearch
from utils import fmt_timedelta

# Set up logging to both stout and to a file
import logging, logging.handlers

logger = logging.getLogger("")
logger.setLevel(logging.INFO)
# logger.setLevel(logging.DEBUG)
file_handler = logging.handlers.RotatingFileHandler(
    "data/scraper.log", maxBytes=(1048576 * 5)
)
sterr_handler = logging.StreamHandler(sys.stderr)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
for handler in [file_handler, sterr_handler]:
    handler.setFormatter(formatter)
    logger.addHandler(handler)

logger.critical("Starting...")


def our_filter(prop, config, search_info, verbose = False):
    if prop.availableFrom != None and prop.availableFrom < config["start_date"]:
        return False
    if prop.isStudio == True:
        return False
    if prop.isShared == True:
        return False
    if prop.isLive == False:
        return False
    if prop.letAgreed == True:
        return False

    if prop.acceptsProfessionals == False:
        return False
    if prop.agent == "OpenRent":
        return False  # use lowercase openrent for our own searches on openrent

    if (
        search_info.min_size_square_meters
        and prop.size
        and prop.size < search_info.min_size_square_meters
    ):
        if verbose: logger.info(f"🧘🏽 {prop.id} is too small at {prop.size}m^2")
        return False  # too small
    if (
        search_info.max_price
        and (prop.includesBills in [None, False])
        and prop.price > search_info.max_price
    ):
        if verbose: logger.info(f"💰 {prop.id} is too expensive at £{prop.price}")
        return False
    if (
        search_info.max_price_with_bills
        and (prop.includesBills == True)
        and prop.price > search_info.max_price_with_bills
    ):
        if verbose: logger.info(f"💰 {prop.id} is too expensive at £{prop.price} with bills")
        return False

    prop.keywords = []
    if prop.description:

        # Filter out agents that start with "We are proud to"
        if re.match("^we are[ ]?[\S]* proud", prop.description.lower()):
            if verbose: logger.info(f"😡 {prop.id} is from an agent.")
            return False

        prop.keywords = [k for k in search_info.keywords if k in prop.description.lower()]
        if search_info.keywords and not prop.keywords: 
            if verbose: logger.info(f"🗝️ {prop.id} doesn't contain any keywords.")
            return False

    return True


def load_config():
    "Load the config with a json parser that allows trailing commas"
    with open("data/config.yml") as f:
        return yaml.safe_load(f)


def load_seen_properties(fname):
    # get our local list of properties we've already seen
    p = Path(fname)
    if not p.exists():
        logger.critical(f"{p} does not exist, creating it.")
        p.touch()

    with open(p, "r") as f:
        checked_property_ids = set(i for i in f.read().split("\n") if i != "")

    return checked_property_ids


@dataclass
class Search:
    name: str
    url: str
    max_price: Optional[float] = None
    max_price_with_bills: Optional[float] = None
    min_size_square_meters: Optional[float] = None
    keywords: list[str] = field(default_factory=list)


def search_properties(config, filter=None, already_seen=None):
    "Return properties from search urls in config, with optional filter function and already_seen set"
    config["start_date"] = dateutil.parser.parse(
        str(config["start_date"]), default=datetime.now(timezone.utc)
    )
    all_properties = {}

    with requests.session() as s:
        for i, search_info in enumerate([Search(**s) for s in config["searches"]]):
            netloc = urlparse(search_info.url).netloc

            if netloc.endswith("openrent.co.uk"):
                search = OpenRentSearch(search_info.name, search_info.url)

            elif netloc.endswith("rightmove.co.uk"):
                search = RightmoveSearch(search_info.name, search_info.url)

            else:
                raise ValueError(f"Don't (yet) know how to scrape {netloc}.")

            # do the search
            search.make_request(s)

            # Filter the results based on criteria
            search.filter(lambda p: our_filter(p, config, search_info))
            logger.info(f"{len(search.properties)} of the results match our criteria.")

            # Ignore anything we've already seen
            search.filter(lambda p: p.id not in already_seen)
            logger.info(f"{len(search.properties)} of those are new to us.")

            # update the list of known properties
            with open(config["checked_properties_list"], "a") as f:
                if len(search.properties.keys()) > 0:
                    f.write("\n" + "\n".join(str(i) for i in search.properties.keys()))

            # Grab any extra info that requires making per property requests
            # Do this after filtering out the obvious ones you don't want
            search.more_info(s)

            # Do an extra filter pass in case this extra info means that we now don't pass the test
            search.filter(lambda p: our_filter(p, config, search_info, verbose=True))
            logger.info(
                f"{len(search.properties)} of the results match our criteria after getting extra info."
            )

            all_properties.update(search.properties)

    return all_properties


# pull in config data
config = load_config()
already_seen_ids = load_seen_properties(config["checked_properties_list"])
all_properties = search_properties(
    config, filter=our_filter, already_seen=already_seen_ids
)
hostname = config.get("hostname", "dev_environment")
logger.info(f"Overall we found {len(all_properties)} new properties.")
# if len(all_properties) == 0: sys.exit()

slack_token = config["slack_token"]
sc = WebClient(token=slack_token)


def floorplan(url):
    return {
        "type": "image",
        "title": {"type": "plain_text", "text": "Floorplan", "emoji": True},
        "image_url": url,
        "alt_text": "Floor Plan",
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
{f"Nearest Station: {p.nearestStation}" if p.nearestStation else ""}
{f"Keywords: {' '.join(s.capitalize() for s in p.keywords)}" if p.keywords else ""}
{p.description}
            """,
        },
        "accessory": {
            "type": "image",
            "image_url": p.imgUrl,
            "alt_text": "Image of the flat",
        },
    }


DIVIDER_BLOCK = {"type": "divider"}

header = {
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": (f"Found {len(all_properties)} new properties!"),
    },
}

# post a message that the bot ran to a differnt channel
sc.chat_postMessage(
    channel=config.get("debug_slack_channel") or "bot_testing",
    text=f"Ran at {datetime.now().strftime('%d %b %y %H:%M')} on {hostname}, found {len(all_properties)} new properties",
)

logger.debug(f"Properties: {all_properties}")
for id_, prop in all_properties.items():
    blocks = [
        property_description(prop),
    ]
    # if prop.floorPlanUrl: blocks.append(floorplan(prop.floorPlanUrl))

    sc.chat_postMessage(
        channel=prop.slack_channel or config.get("slack_channel") or "openrent",
        text="New property found!",
        blocks=blocks,
    )
    time.sleep(0.1)