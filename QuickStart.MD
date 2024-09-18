# Step 1
Install requirements with: pip install -r requirements.txt

# Step 2
Create a config.py with the Variables imported in the script.

i.e looking like this
-----------------------------------------------------------------
import logging

DEBUG = False
LOGLEVEL = logging.INFO
SCOPES = ["https://www.googleapis.com/auth/calendar"]
LOGPATH = './data/log/'
GAMEDBPATH = './data/game.db'
CALENDARDBPATH = './data/calendar.db'
PROBASKETCLUBS = [
	{'clubId': 'xxx', 'includeAll': True}, 
	{'clubId': 'yyy', 'includeAll': False, 'leagues': ['D2LA']}
]
NAMEREPLACEMENTS = ['Test']
CLUBNAME = 'Club-Name'
CLUBNAMESHORT = 'Short Club-Name'
CLUBGAMESURL = 'https://probasket.ch/season.php'
-----------------------------------------------------------------
The Club Id can be found at https://www.probasket.ch/generator.php

# Step 3
Verify that the Paths for the databases exist

# Step 4
Create a Google Cloud Project and activate the Calendar API

# Step 5
Put the credentials.json and token.json files in the root directory of this project