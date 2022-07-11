# Openrent/Rightmove Unofficial Api
<img width="697" alt="image" src="https://user-images.githubusercontent.com/2063944/172571819-f942bd88-68b4-4752-b74e-0bcdfeb005b6.png">
Parses the script tags embedded in openrent.co.uk and rightmove.co.uk pages to create a rudimentary API. I'm using it to post new properties that match certain criteria to a slack channel.

To use: 

- Rename example_config.json -> config.json and fill it out with a slack bot token, start date, and some search urls from openrent or Rightmove
- install requirements.txt
- run scraper.py with python >3.8, possibly with a cron job.

