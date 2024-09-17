from config import DEBUG, LOGLEVEL, SCOPES, GAMEDBPATH, CALENDARDBPATH, PROBASKETCLUBID, CLUBNAME, CLUBNAMESHORT
import datetime
import os.path
import requests
import json
from bs4 import BeautifulSoup
from pprint import pprint
import random
import string
import os
import sqlite3
import logging
import time
from logging.handlers import TimedRotatingFileHandler


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


#region Functions
def main():
    setupLogging()
    logStartTime()
    authenticate()
    updateGames()
    updateCalendars()
    checkGames()
    logEndTime()


def logStartTime():
    global startTime
    startTime = time.time()
    logging.info(f"Start time: {time.ctime(startTime)}")


def logEndTime():
    endTime = time.time()
    duration = round(endTime - startTime, 1)
    logging.info(f"End time: {time.ctime(endTime)}")
    logging.info(f"Duration: {duration} seconds")


def authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logging.error(f"Error refreshing access token: {e}")
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_console()
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
                logging.error(f"Error refreshing access token: {e}")
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())

    return creds


def getService():
    creds = getCreds()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    return service


def updateEvent(loadedGame, field, calendarId, case = 'update'):
    # The calendar ID can be found in the settings of the Google Calendar 
    try:
        service = getService()

        startDateTime = datetime.datetime.strptime(loadedGame['date'], '%Y-%m-%d %H:%M:%S')
        endDateTime = startDateTime + datetime.timedelta(hours=2)

        event = {
            'summary': f'{loadedGame["league"]} {loadedGame["homeTeam"]} vs. {loadedGame["awayTeam"]}',
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
            event = service.events().patch(calendarId=calendarId, eventId=loadedGame[{field}], body=event).execute()
        if case == 'create':
            event = service.events().insert(calendarId=calendarId, body=event).execute()
            # Update the game with the new event ID
            updateGameDB(loadedGame['id'], field, event['id'])
        
        return True

    except HttpError as error:
        logging.error(f"An error occurred: {error}")
        return False


def checkGames():
    loadedGames = loadGames() or []
    loadedCalendars = loadCalendars() or []
    calendarEvents = fetchCalendarEvents(loadedCalendars) or []
    clubCalendarId = loadCalendar('isClubCalendar', 1)['googleCalendarId']
    
    createdClubGamesCount = 0
    updatedClubGamesCount = 0
    unchangedClubGamesCount = 0
    createdTeamGamesCount = 0
    updatedTeamGamesCount = 0
    unchangedTeamGamesCount = 0
    noDateGamesCount = 0

    for game in loadedGames:
        # Check if the game has a related teamCalendar id
        if game['teamCalendarId'] == None:
            # Calendars should already be created, so we can just check if the calendar exists
            calendar = checkCalendarExists(game['league'])
            if calendar != None:
                updateGameDB(game['id'], 'teamCalendarId', calendar['googleCalendarId'])
                game['teamCalendarId'] = calendar['googleCalendarId']
            else:
                logging.warning(f"Calendar for league {game['league']} not found")
                continue

        if game['date'] == None or game['date'] == '':
            logging.warning(f"Game with id {game['id']} has no date set. Unable to create an Calendar Event.")
            noDateGamesCount += 1
            continue

        # Club-Calendar
        if game['clubCalendarEventId'] == None:
            # create event in club calendar
            updateEvent(game, 'clubCalendarEventId', clubCalendarId, 'create')
            createdClubGamesCount += 1
            logging.info(f"Created game with id {game['id']}")
        else:
            # check by field id if game is in calendarevents
            for event in calendarEvents:
                if (event['id'] == game['clubCalendarEventId']):
                    if not compareGame(game, event):
                        # update event in club calendar
                        updateEvent(game, 'clubCalendarEventId', clubCalendarId, 'update')
                        updatedClubGamesCount += 1
                        logging.info(f"Updated game with id {game['id']} in Club-Calendar")
                    else:
                        unchangedClubGamesCount += 1
                    break

        # Team-Calendar
        if game['teamCalendarEventId'] == None:
            # create event in team calendar
            updateEvent(game, 'teamCalendarEventId', game['teamCalendarId'], 'create')
            createdTeamGamesCount += 1
            logging.info(f"Created game with id {game['id']}")
        else:
            # check by field id if game is in calendarevents
            for event in calendarEvents:
                if (event['id'] == game['teamCalendarEventId']):
                    if not compareGame(game, event):
                        # update event in team calendar
                        updateEvent(game, 'teamCalendarEventId', game['teamCalendarId'], 'update')
                        updatedTeamGamesCount += 1
                        logging.info(f"Updated game with id {game['id']} in Team-Calendar")
                    else:
                        unchangedTeamGamesCount += 1
                    break

    logging.info(f"Games without date: {noDateGamesCount}")
    logging.info(f"Created Club-Calendar Events: {createdClubGamesCount}")
    logging.info(f"Updated Club-Calendar Events: {updatedClubGamesCount}")
    logging.info(f"Unchanged Club-Calendar Events: {unchangedClubGamesCount}")
    logging.info(f"Created Team-Calendar Events: {createdTeamGamesCount}")
    logging.info(f"Updated Team-Calendar Events: {updatedTeamGamesCount}")
    logging.info(f"Unchanged Team-Calendar Events: {unchangedTeamGamesCount}")


def createGameTable(conn):
    # Create a cursor object
    c = conn.cursor()

    # Create table
    c.execute('''
        CREATE TABLE game (
            id text PRIMARY KEY,
            day text NULL,
            date DATETIME NULL,
            league text,
            homeTeam text,
            awayTeam text,
            gym text,
            result text,
            clubCalendarEventId text NULL,
            teamCalendarEventId text NULL,
            teamCalendarId text,
            FOREIGN KEY (teamCalendarId) REFERENCES calendar(id)
        )
    ''')


def createCalendarTable(conn):
    # Create a cursor object
    c = conn.cursor()

    # Create table
    c.execute('''
        CREATE TABLE calendar (
            id text PRIMARY KEY,
            googleCalendarId text,
            league text NULL,
            isClubCalendar boolean
        )
    ''')


def loadGames():
    try:
        conn = sqlite3.connect(GAMEDBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT * FROM game
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


def loadCalendars():
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        c.execute(f'''
            SELECT * FROM calendar
        ''')

        calendars = c.fetchall()

        # Convert sqlite3.Row objects to dictionaries
        calendars = [dict(calendar) for calendar in calendars]

        conn.close()
        return calendars
    except sqlite3.Error as e:
        logging.error(f"An error occurred: {e}")
        return None


def loadCalendar(field, value):
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        c.execute(f'''
            SELECT * FROM calendar
            WHERE {field} = :value
        ''', {'value': value})

        calendar = c.fetchone()

        # Convert sqlite3.Row object to dictionary
        calendar = dict(calendar)

        conn.close()
        return calendar
    except sqlite3.Error as e:
        logging.error(f"An error occurred: {e}")
        return None


def findLeagues():
    try:
        conn = sqlite3.connect(GAMEDBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT DISTINCT league FROM game
        ''')

        leagues = c.fetchall()

        # Convert sqlite3.Row objects to dictionaries
        leagues = [dict(league) for league in leagues]

        conn.close()
        return leagues
    except sqlite3.Error as e:
        logging.error(f"An error occurred: {e}")
        return []


def updateGames():
    url = 'https://probasket.ch/season.php'
    params = {
        'club': PROBASKETCLUBID,
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

        id = elements[2].text + '_' + elements[3].text + '_' + elements[4].text + '_' + getRandom()
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
            'clubCalendarEventId': None,
            'teamCalendarEventId': None,
            'teamCalendarId': None
        }

        gamesList.append(gameObj)

    # pprint(gamesList, indent=4)

    # Check if the database file exists before creating the gametable
    if not os.path.exists(GAMEDBPATH):
        # Create a connection to the SQLite database
        conn = sqlite3.connect(GAMEDBPATH)
        createGameTable(conn)
        conn.close()

    # Insert the games into the table
    conn = sqlite3.connect(GAMEDBPATH)
    c = conn.cursor()

    for game in gamesList:
        # Attempt to insert the new game, ignoring the operation if the game already exists
        c.execute('''
            INSERT OR IGNORE INTO game (id, day, date, league, homeTeam, awayTeam, gym, result)
            VALUES (:id, :day, :date, :league, :homeTeam, :awayTeam, :gym, :result)
        ''', game)

        # Update the game if it already exists, excluding the clubCalendarEventId field
        c.execute('''
            UPDATE game
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


def updateCalendars():
    leagues = findLeagues()
    
    # create club calendar
    createCalendarDB(None, True)

    # create team calendars
    for league in leagues:
        createCalendarDB(league['league'])


def createCalendarDB(league=None, isClubCalendar=False):
    # Check if the database file exists before creating the gametable
    if not os.path.exists(CALENDARDBPATH):
        try:
            # Create a connection to the SQLite database
            conn = sqlite3.connect(CALENDARDBPATH)
            createCalendarTable(conn)
        except sqlite3.Error as e:
            print(f"An error occurred: {e}")
        finally:
            if conn:
                conn.close()

    # Check if the league already exists in the database
    if checkCalendarExists(league):
        return
    else:
        try:
            # Create a new Google Calendar
            googleCalendarId = createGoogleCalendar(league)

            # Create a connection to the SQLite database
            conn = sqlite3.connect(CALENDARDBPATH)
            c = conn.cursor()

            if (league == None):
                league = 'club'

            # Insert the new calendar into the table
            c.execute('''
                INSERT INTO calendar (id, googleCalendarId, league, isClubCalendar)
                VALUES (:id, :googleCalendarId, :league, :isClubCalendar)
            ''', {
                'id': league + '_' + getRandom(),
                'googleCalendarId': googleCalendarId,
                'league': league,
                'isClubCalendar': isClubCalendar
            })

            # Commit the changes
            conn.commit()
        except sqlite3.Error as e:
            print(f"An error occurred: {e}")
        finally:
            if conn:
                conn.close()


def checkCalendarExists(league = None):
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        if league != None:
            c.execute('''
                SELECT * FROM calendar
                WHERE league = :league
            ''', {'league': league})
        else:
            c.execute('''
                SELECT * FROM calendar
                WHERE isClubCalendar = 1
            ''')

        calendar = c.fetchone()

        conn.close()
        return calendar
    except sqlite3.Error as e:
        logging.error(f"An error occurred: {e}")
        return None


def updateGameDB(id, field, value):
    try:
        conn = sqlite3.connect(GAMEDBPATH)
        c = conn.cursor()
        logging.info(f"Attempting to update game with id {id}: Field {field} with value {value}")

        query = f'''
            UPDATE game
            SET {field} = :value
            WHERE id = :id
        '''
        c.execute(query, {'id': id, 'value': value})

        logging.info(f"Rows updated: {c.rowcount}")

        conn.commit()
    except sqlite3.Error as e:
        logging.error(f"An error occurred: {e}")
    finally:
        conn.close()


def createGoogleCalendar(league = None):
    try:
        service = getService()
        if league != None:
            calendarName = CLUBNAMESHORT + ' ' + league
        else:
            calendarName = CLUBNAME

        calendar = {
            'summary': calendarName,
            'timeZone': 'Europe/Zurich'
        }

        created_calendar = service.calendars().insert(body=calendar).execute()

        return created_calendar['id']
    except HttpError as error:
        logging.error(f"An error occurred: {error}")


def fetchCalendarEvents(loadedCalendars):
    allEvents = []
    for calendar in loadedCalendars:
        events = fetchEvents(calendar)
        if events != None:
            allEvents.extend(events)

    return allEvents


def fetchEvents(calendar):
    try:
        service = getService()
        #   now = datetime.datetime.utcnow().isoformat() + "Z"
        # The calendar ID can be found in the settings of the Google Calendar (this is the id of the EB calendar)
        events_result = service.events().list(calendarId=calendar['googleCalendarId'], maxResults=500, singleEvents=True, orderBy="startTime").execute()
        events = events_result.get("items", [])

        if not events:
            logging.info(f"No events found for calendar {calendar['league']}")
            return

        return events

    except HttpError as error:
      logging.error(f"An error occurred: {error}")


def compareGame(game, calendarEvent):
    # Compare the game data with the calendar event data
    # Return True if they match, False otherwise
    return (
        datetime.datetime.strptime(game['date'], '%Y-%m-%d %H:%M:%S') == datetime.datetime.strptime(calendarEvent['start']['dateTime'], '%Y-%m-%dT%H:%M:%S+02:00') and
        game['gym'] == calendarEvent['location']
    )


def getRandom():
    characters = string.ascii_letters + string.digits
    return ''.join(random.choices(characters, k=8))


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
    
    # Set the format for the log messages, including a timestamp and function name
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    
    # Get the root logger and configure it with the handler
    logger = logging.getLogger()
    logger.setLevel(LOGLEVEL)
    logger.addHandler(handler)


#region Main

if __name__ == "__main__":
    main()