import requests
import json
from bs4 import BeautifulSoup
from pprint import pprint
import os
import sqlite3

dbPath = './data/games.db'

def create_table(conn):
    # Create a cursor object
    c = conn.cursor()

    # Create table
    c.execute('''
        CREATE TABLE games (
            id text PRIMARY KEY,
            day text,
            date text,
            homeTeam text,
            awayTeam text,
            gym text,
            result text
        )
    ''')

url = 'https://probasket.ch/season.php'
params = {
    'club': '163',
    'jsoncallback': 'jsoncallback'
}

response = requests.get(url, params=params)

# The response is expected to be in JSONP format, which is essentially a function call in JavaScript.
# We need to strip out the function call to get the actual JSON data.
# Assuming the response is something like `jsoncallback({...})`, we can do the following:

# Remove the leading 'jsoncallback(' and trailing ');'
json_data = response.text[13:-2]

# Convert the JSON data to a Python dictionary
data = json.loads(json_data)

soup = BeautifulSoup(data['html'], 'html.parser')

games = soup.find_all('tr')
gamesList = []
for game in games:
    if game == games[0]:
        continue
    elements = game.find_all('td')
    gameObj = {
        'day': elements[0].text,
        'date': elements[1].text,
        'homeTeam': elements[2].text,
        'awayTeam': elements[3].text,
        'gym': elements[4].text,
        'result': elements[5].text
    }

    gamesList.append(gameObj)

# pprint(gamesList, indent=4)

# Check if the database file exists before creating the table
if not os.path.exists(dbPath):
    # Create a connection to the SQLite database
    conn = sqlite3.connect(dbPath)
    create_table(conn)
    conn.close()

# Insert the games into the table
conn = sqlite3.connect(dbPath)
c = conn.cursor()

for game in gamesList:
    # Create a unique identifier for each game
    game_id = game['homeTeam'] + game['awayTeam']
    game['id'] = game_id

    c.execute('''
        INSERT OR REPLACE INTO games VALUES (
            :id,
            :day,
            :date,
            :homeTeam,
            :awayTeam,
            :gym,
            :result
        )
    ''', game)

# Commit the changes and close the connection
conn.commit()
conn.close()