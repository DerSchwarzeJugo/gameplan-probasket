import requests
from bs4 import BeautifulSoup

# Define the URL to send the POST request to
url = 'https://basketplan.ch/showSearchGames.do'

# Create a dictionary for the data payload
data = {
    'actionType': 'searchGames',
    'from': '01.07.24',
    'federationId': '10',
    'clubId': '163',
    'maxResult': '500'
}

# Send the POST request
response = requests.post(url, data=data)

# Check if the request was successful
if response.status_code == 200:
    # Parse the HTML response
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the table with the game data
    table = soup.select_one('#body table.forms')
    
    # Extract specific game data from the table rows, skipping the first two rows
    games = []
    rows = table.find_all('tr')[2:]  # Skip the first two rows
    for row in rows:
        cells = row.find_all('td')
        game_data = {
            'date': cells[0].text.strip(),
            'league': cells[3].text.strip(),
            'gameId': cells[5].text.strip(),
            'gym': cells[6].text.strip(),
            'homeTeam': cells[7].text.strip(),
            'awayTeam': cells[8].text.strip(),
            'score': cells[11].text.strip(),
        }
        games.append(game_data)
    
    # Print the extracted game data
    print(games)
else:
    print(f"Failed to retrieve data. Status code: {response.status_code}")