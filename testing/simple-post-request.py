# this loads from basketplan.ch directly and therefore has the gamenumber included, which could be used as a unique identifier

import requests

# Define the URL to send the POST request to
url = 'https://basketplan.ch/showSearchGames.do'

# Create a dictionary for the data payload
data = {
	'actionType': 'searchGames',
	'from': '01.07.24',
    'clubId': '163',
}

# Send the POST request
response = requests.post(url, data=data)

# Print the response
print(response.text)