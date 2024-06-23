# Description: This script is used to update the Google Calendar with the latest basketball games from the ProBasket website for a provided club ID. For a new season, just delete/archive the games.db and allow for a new one to be created. The script will create a new event for each game that does not have a calendar event ID, and update the event if the game data has changed

import datetime
import os.path
import requests
import json
from bs4 import BeautifulSoup
from pprint import pprint
import os
import sqlite3
import logging
from logging.handlers import TimedRotatingFileHandler


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


#region Constants
DEBUG = True
SCOPES = ["https://www.googleapis.com/auth/calendar"]
DBPATH = './data/games.db'
CALENDARID = "925a0d61e624b1742abf37419fb1ff0777c5b40cb1166d8be0c6b42d7f6432a2@group.calendar.google.com"


#region Functions
def main():
    setupLogging()
    authenticate()
    updateGames()
    checkGames()


def authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                log(f"Error refreshing access token: {e}",'error')
                creds = None
            if not creds:
                flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
                creds = flow.run_local_server(port=0)
                with open("token.json", "w") as token:
                    token.write(creds.to_json())


def getCreds():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                log(f"Error refreshing access token: {e}", 'error')
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())

    return creds


def getService():
    creds = getCreds()
    service = build("calendar", "v3", credentials=creds)
    return service


def updateEvent(loadedGame, case = 'update'):
    # The calendar ID can be found in the settings of the Google Calendar (this is the id of the EB calendar)
    try:
        service = getService()

        startDateTime = datetime.datetime.strptime(loadedGame['date'], '%Y-%m-%d %H:%M:%S')
        endDateTime = startDateTime + datetime.timedelta(hours=2)

        event = {
            'summary': f'Basket: {loadedGame["league"]} {loadedGame["homeTeam"]} vs. {loadedGame["awayTeam"]}',
            'location': loadedGame['gym'],
            'start': {
                'dateTime': startDateTime.isoformat() + '+02:00',
                'timeZone': 'Europe/Zurich',
            },
            'end': {
                'dateTime': endDateTime.isoformat() + '+02:00',
                'timeZone': 'Europe/Zurich',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                {'method': 'popup', 'minutes': 120},
                ],
            },
        }

        if case == 'update':
            event = service.events().patch(calendarId=CALENDARID, eventId=loadedGame['calendarEventId'], body=event).execute()
        if case == 'create':
            event = service.events().insert(calendarId=CALENDARID, body=event).execute()
            updateGameDB(loadedGame['id'], event['id'])

    except HttpError as error:
        log(f"An error occurred: {error}", "error")


def checkGames():
    loadedGames = loadGames() or []
    calendarEvents = fetchCalendarEvents() or []
    
    createdGamesCount = 0
    updatedGamesCount = 0
    unchangedGamesCount = 0
    for game in loadedGames:
        if game['calendarEventId'] == None:
            updateEvent(game, 'create')
            createdGamesCount += 1
            log(f"Created game with id {game['id']}", "info")
        else:
            # check by field id if game is in calendarevents
            for event in calendarEvents:
                if (event['id'] == game['calendarEventId']):
                    if not compareGame(game, event):
                        updateEvent(game, 'update')
                        updatedGamesCount += 1
                        log(f"Updated game with id {game['id']}", "info")
                    else:
                        unchangedGamesCount += 1
                    break
    
    log(f"Created {createdGamesCount} games and updated {updatedGamesCount} games", "info")
    log(f"Unchanged games: {unchangedGamesCount}", "info")


def createTable(conn):
    # Create a cursor object
    c = conn.cursor()

    # Create table
    c.execute('''
        CREATE TABLE games (
            id text PRIMARY KEY,
            day text,
            date DATETIME,
            league text,
            homeTeam text,
            awayTeam text,
            gym text,
            result text,
            calendarEventId text NULL
        )
    ''')


def loadGames():
    try:
        conn = sqlite3.connect(DBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT * FROM games
        ''')

        games = c.fetchall()

        # Convert sqlite3.Row objects to dictionaries
        games = [dict(game) for game in games]

        if (DEBUG):
            # trim to 2 games only for testing
            games = games[:2]

        conn.close()
        return games
    except sqlite3.Error as e:
        logging.error(f"An error occurred: {e}")
        return []


def updateGames():
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

        id = elements[2].text + '_' + elements[3].text + '_' + elements[4].text
        id = id.replace(' ', '_').lower()

        date = elements[1].text
        dateObj = datetime.datetime.strptime(date, '%d.%m.%Y, %H:%M')

        gameObj = {
            'id': id,
            'day': elements[0].text,
            'date': dateObj,
            'league': elements[2].text,
            'homeTeam': elements[3].text,
            'awayTeam': elements[4].text,
            'gym': elements[5].text,
            'result': elements[6].text,
            'calendarEventId': None
        }

        gamesList.append(gameObj)

    # pprint(gamesList, indent=4)

    # Check if the database file exists before creating the table
    if not os.path.exists(DBPATH):
        # Create a connection to the SQLite database
        conn = sqlite3.connect(DBPATH)
        createTable(conn)
        conn.close()

    # Insert the games into the table
    conn = sqlite3.connect(DBPATH)
    c = conn.cursor()

    for game in gamesList:
        # Attempt to insert the new game, ignoring the operation if the game already exists
        c.execute('''
            INSERT OR IGNORE INTO games (id, day, date, league, homeTeam, awayTeam, gym, result)
            VALUES (:id, :day, :date, :league, :homeTeam, :awayTeam, :gym, :result)
        ''', game)

        # Update the game if it already exists, excluding the calendarEventId field
        c.execute('''
            UPDATE games
            SET day = :day,
                date = :date,
                league = :league,
                homeTeam = :homeTeam,
                awayTeam = :awayTeam,
                gym = :gym,
                result = :result
            WHERE id = :id
        ''', game)

    # Commit the changes and close the connection
    conn.commit()
    conn.close()


def updateGameDB(id, calendarEventId):
    try:
        conn = sqlite3.connect(DBPATH)
        c = conn.cursor()
        log(f"Attempting to update game with id {id} with calendarEventId {calendarEventId}", "info")

        c.execute('''
            UPDATE games
            SET calendarEventId = :calendarEventId
            WHERE id = :id
        ''', {'id': id, 'calendarEventId': calendarEventId})

        log(f"Rows updated: {c.rowcount}", "info")

        conn.commit()
    except sqlite3.Error as e:
        log(f"An error occurred: {e}", "error")
    finally:
        conn.close()


def fetchCalendarEvents():
    try:
        service = getService()
        #   now = datetime.datetime.utcnow().isoformat() + "Z"
        # The calendar ID can be found in the settings of the Google Calendar (this is the id of the EB calendar)
        events_result = service.events().list(calendarId=CALENDARID, maxResults=500, singleEvents=True, orderBy="startTime").execute()
        events = events_result.get("items", [])

        if not events:
            log("No events found.", "info")
            return

        return events

    except HttpError as error:
      log(f"An error occurred: {error}", "error")


def compareGame(game, calendarEvent):
    # Compare the game data with the calendar event data
    # Return True if they match, False otherwise
    return (
        datetime.datetime.strptime(game['date'], '%Y-%m-%d %H:%M:%S') == datetime.datetime.strptime(calendarEvent['start']['dateTime'], '%Y-%m-%dT%H:%M:%S+02:00') and
        game['gym'] == calendarEvent['location']
    )


def setupLogging():
    # Ensure the log directory exists
    log_directory = './data/log/'
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)
    
    # Create a handler that writes log messages to a file, with a new file created each day
    handler = TimedRotatingFileHandler(
        filename=os.path.join(log_directory, 'app.log'),
        when='midnight',  # Rotate at midnight
        interval=1,  # Interval is 1 day
        backupCount=30,  # Keep 30 days of logs
        encoding='utf-8',  # Use utf-8 encoding for the log files
    )
    
    # Set the format for the log messages
    formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    
    # Get the root logger and configure it with the handler
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)


def log(message, level="info"):
    if level == "info":
        logging.info(message)
    elif level == "warning":
        logging.warning(message)
    elif level == "error":
        logging.error(message)
    elif level == "debug":
        logging.debug(message)
    else:
        logging.info("Unknown logging level: " + message)


#region Main

if __name__ == "__main__":
    main()