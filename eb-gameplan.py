import requests
import json
from bs4 import BeautifulSoup
from pprint import pprint

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

# Now you can use the data as you wish. For example, print the HTML:
# print(data['html'])

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

pprint(gamesList, indent=4)