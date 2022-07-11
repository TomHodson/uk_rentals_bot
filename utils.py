from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import islice
from random import randint

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
    
    bedrooms : int = None
    bathrooms : int = None
    hasGarden : bool = None
    isFurnished : bool = None
    
    latitude : float = None
    longitude : float = None
    nearestStation: str = None

    isLive : bool = None
    letAgreed : bool = None

def random_chunk(li, min_chunk=5, max_chunk=19):
    "split a list into randomly sized chunks"
    it = iter(li)
    while True:
        nxt = list(islice(it,randint(min_chunk,max_chunk)))
        if nxt:
            yield nxt
        else:
            break

def fmt_timedelta(dt):
    timedelta = datetime.now(timezone.utc) - dt
    n = timedelta.total_seconds() / 3600

    if n < 24: return f"{n:.0f} hours"
    if n < 24 * 7: return f"{n/24:.0f} days"
    if n < 24 * 7 * 4: return f"{n/24/7:.0f} weeks"
    if n < 24 * 7 * 4 * 12: return f"{n/24/7/4:.0f} months"
    return f"{n/24/7/4/12:.0f} years"