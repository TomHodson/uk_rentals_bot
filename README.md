# Openrent Unofficial Api
Parses the script tags embedded in openrent.co.uk pages to create a rudimentary API. I'm using it to post new properties that match certain criteria to a slack channel.


To use: 

- Rename example_config.json -> config.json and fill it out with a slack bot token, start date, and some search urls from openrent
- install requirements.txt
- run scrap.py with python >3.8, possibly with a cron job.

