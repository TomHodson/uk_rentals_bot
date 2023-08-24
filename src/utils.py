from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import islice
from random import randint
import numpy as np

@dataclass
class Property:
    id : tuple
    title : str = None
    description : str = None
    size: float = None
    
    price : float = None
    includesBills : bool = None
    
    url : str = None
    imgUrl : str = None
    floorPlanUrl : str = None
    
    agent : str = None
    contactTelephone : str = None

    availableFrom : datetime = None
    listedAt : datetime = None
    minimumTenancy : int = None

    isStudio : bool = None
    isShared : bool = None
    acceptsProfessionals : bool = None
    maximumTenants : int = None
    
    bedrooms : int = None
    bathrooms : int = None
    hasGarden : bool = None
    isFurnished : bool = None
    
    latitude : float = None
    longitude : float = None
    nearestStation: str = None

    isLive : bool = None
    letAgreed : bool = None

    rawData : dict = None
    slack_channel : str = None

def random_chunk(li, min_chunk=5, max_chunk=19):
    "split a list into randomly sized chunks"
    it = iter(li)
    while True:
        nxt = list(islice(it,randint(min_chunk,max_chunk)))
        if nxt:
            yield nxt
        else:
            break

def pairs(li):
    "split a list into randomly sized chunks"
    i = iter(li)
    while True:
        nxt = list(islice(i,2))
        if nxt:
            yield nxt
        else:
            break

def fmt_timedelta(dt):
    timedelta = datetime.now(timezone.utc) - dt
    
    time_units = [
        (60, "second"),
        (60, "minute"),
        (24, "hour"),
        (7, "day"),
        (4, "week"),
        (12, "month"),
        (np.inf, "year")
    ]

    #start in seconds and iteratively find the largest interval
    value = timedelta.total_seconds()
    if round(value) < 1: return "less than a second"
    for next_size, unit_name in time_units:
        if value < next_size: return f"{value:.0f} {unit_name}{'s' if round(value) > 1 else ''}"
        value = value / next_size