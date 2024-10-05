# Step 1
Install requirements with: pip install -r requirements.txt

# Step 2
Create a config.py with the Variables imported in the script.

i.e looking like this
-----------------------------------------------------------------
```
import logging

DEBUG = False # this reduces the created events to two elements for testing
LOGLEVEL = logging.INFO # define what loglevel should be used for the output of the log
SCOPES = ["https://www.googleapis.com/auth/calendar"]
LOGPATH = './data/log/'
GAMEDBPATH = './data/game.db'
CALENDARDBPATH = './data/calendar.db'
PROBASKETCLUBS = [
	{'clubId': 'xxx', 'includeAll': True}, 
	{'clubId': 'yyy', 'includeAll': False, 'leagues': ['D2LA']}
]
CLUBNAME = '<Club-Name>'
CLUBNAMESHORT = '<Short Club-Name>'
CLUBGAMESURL = 'https://basketplan.ch/showSearchGames.do'
GOTIFYURL = '<url>'
GOTIFYTOKEN = '<token>'
SERVICEACCOUNTFILE = './service-account.json'
```
-----------------------------------------------------------------
The Club Id can be found at https://www.probasket.ch/generator.php

# Step 3
Verify that the Paths for the databases and for logging exists

# Step 4
Create a Google Cloud Project and activate the Calendar API. Create a Service Account, create Keys for it and download the json file.

# Step 5
Put the right path to the credentials file into the config file.

# Step 6
If you want you can add sending notifications with gotify