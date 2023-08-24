# Openrent/Rightmove Unofficial Api
<img width="697" alt="image" src="https://user-images.githubusercontent.com/2063944/172571819-f942bd88-68b4-4752-b74e-0bcdfeb005b6.png">
Parses the script tags embedded in openrent.co.uk and rightmove.co.uk pages to create a rudimentary API. I'm using it to post new properties that match certain criteria to a slack channel.

To use: 

```
cp example_config.json config.json
# add your slack token and settings to config.json
mamba env create --name rentbot
mamba activate rentbot
pip install -r requirements.txt
python src/scrape.py
```

- Rename example_config.json -> config.json and fill it out with a slack bot token, start date, and some search urls from openrent or Rightmove
- install requirements.txt
- run scraper.py with python >3.8, possibly with a cron job.

# How does it work?

## Rightmove 
- Generate a search URL by going to rightmove.co.uk and making a search
- GET it, in the returned HTML there is a script tag that begins `<script> window.jsonModel = ...`grab that and parse it to get data about the first 25 properties associated with a search.
- Haven't implemented getting more than 25 yet.

### Getting extra info on RightMove properties
- pull the property url from the above
- GET it and grab the script tag that begins `window.PAGE_MODEL = ...`, this has more detailed info about each property


## OpenRent
- Generate a search URL by going to openrent.co.uk and making a search
- Look for a script tag that contains "var PROPERTYIDS = ..." and then parse all the variables of the form `var x = y`
- They're all arrays of parameters so reshape it


### Getting more info
- hit https://www.openrent.co.uk/search/propertiesbyid?ids=[id1,id2 ... id20] with the ids of properties you want info on. Max 20 per request
