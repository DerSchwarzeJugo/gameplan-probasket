from config import DEBUG, LOGLEVEL, LOGPATH, SCOPES, GAMEDBPATH, CALENDARDBPATH, PROBASKETCLUBS, CLUBNAME, CLUBNAMESHORT, CLUBGAMESURL, GOTIFYURL, GOTIFYTOKEN
import time
import datetime
import pytz
import locale
import os.path
import requests
from bs4 import BeautifulSoup
import random
import string
import os
import sqlite3
import logging
from logging.handlers import TimedRotatingFileHandler
from dateutil import parser

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

#region Main

def main():
    setupLogging()
    logStartTime()
    authenticate()
    for club in PROBASKETCLUBS:
        updateGames(club)
    updateCalendars()
    checkGames()
    logEndTime()

#endregion

#region Google

def authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logMessage = f"Error refreshing access token: {e}"
                logging.error(logMessage)
                sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
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
                logMessage = f"Error refreshing access token: {e}"
                logging.error(logMessage)
                sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
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
        logMessage = f"An error occured: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)

def fetchEvents(calendar):
    try:
        service = getService()
        events_result = service.events().list(calendarId=calendar['googleCalendarId'], maxResults=500, singleEvents=True, orderBy="startTime").execute()
        events = events_result.get("items", [])

        if not events:
            logging.info(f"No events found for calendar {calendar['league']}")
            return

        return events

    except HttpError as error:
        logMessage = f"An error occurred: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)

def updateEvent(loadedGame, field, calendarId, case='update'):
    try:
        service = getService()
        
        startDateTime = parser.parse(loadedGame['date'])
        zurich_tz = pytz.timezone('Europe/Zurich')
        startDateTime = startDateTime.astimezone(zurich_tz)
        endDateTime = startDateTime + datetime.timedelta(hours=2)

        event = {
            'summary': f'{loadedGame["league"]} {loadedGame["homeTeam"]} vs. {loadedGame["awayTeam"]}',
            'location': loadedGame['gym'],
            'start': {
                'dateTime': startDateTime.isoformat(),
                'timeZone': 'Europe/Zurich',
            },
            'end': {
                'dateTime': endDateTime.isoformat(),
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
            event = service.events().patch(calendarId=calendarId, eventId=loadedGame[field], body=event).execute()
        if case == 'create':
            event = service.events().insert(calendarId=calendarId, body=event).execute()
            updateGameDB(loadedGame['id'], field, event['id'])
        
        return True

    except HttpError as error:
        logMessage = f"An error occurred: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        return False

def fetchCalendarEvents(loadedCalendars):
    allEvents = []
    for calendar in loadedCalendars:
        events = fetchEvents(calendar)
        if events != None:
            allEvents.extend(events)

    return allEvents

#endregion

#region Games

def updateGames(club=None):
    if club is None:
        logMessage = "No club provided"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        return

    logging.debug(f"Updating games for club: {club}")

    url = CLUBGAMESURL
    data = {
        'actionType': 'searchGames',
        'from': '01.07.24',
        'federationId': '10',
        'clubId': club['clubId'],
        'maxResult': '500'
    }
    params = {
        'perspective': 'de_default'
    }

    try:
        response = requests.post(url, data=data, params=params)

        # Check if the request was successful
        if response.status_code == 200:
            # Parse the HTML response
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the table with the game data
            table = soup.select_one('#body table.forms')
            
            # Extract specific game data from the table rows, skipping the first two rows
            gamesList = []
            rows = table.find_all('tr')[2:]  # Skip the first two rows
            for row in rows:
                cells = row.find_all('td')

                league = cells[3].text.strip()
                if not club['includeAll'] and league not in club['includeLeagues']:
                    continue

                # Set locale to German
                locale.setlocale(locale.LC_TIME, 'de_DE')
                date = cells[0].text.strip()
                dateObj = None
                if date != '':
                    # format: Fr 01.07.24 20:00
                    dateObj = datetime.datetime.strptime(date, '%a %d.%m.%y %H:%M')
                    dateObj = pytz.timezone('Europe/Zurich').localize(dateObj)

                gameData = {
                    'date': dateObj,
                    'league': league,
                    'id': cells[5].text.strip(),
                    'gym': cells[6].text.strip(),
                    'homeTeam': cells[7].text.strip(),
                    'awayTeam': cells[8].text.strip(),
                    'result': cells[11].text.strip(),
                }
                gamesList.append(gameData)
            
        else:
            logMessage = f"Failed to retrieve data from Basketplan. Status code: {response.status_code}"
            logging.error(logMessage)
            sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
            return

        if not os.path.exists(GAMEDBPATH):
            try:
                conn = sqlite3.connect(GAMEDBPATH)
                createGameTable(conn)
            except sqlite3.Error as error:
                logMessage = f"An error occured while creating Game Table: {error}"
                logging.error(logMessage)
                sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
            finally:
                if conn:
                    conn.close()

        conn = sqlite3.connect(GAMEDBPATH)
        c = conn.cursor()

        for game in gamesList:

            c.execute('''
                INSERT OR IGNORE INTO game (id, date, league, homeTeam, awayTeam, gym, result)
                VALUES (:id, :date, :league, :homeTeam, :awayTeam, :gym, :result)
            ''', game)

            c.execute('''
                UPDATE game
                SET date = :date,
                    league = :league,
                    homeTeam = :homeTeam,
                    awayTeam = :awayTeam,
                    gym = :gym,
                    result = :result
                WHERE id = :id
            ''', game)

        conn.commit()
        logging.debug("Changes committed")

    except requests.RequestException as req_error:
        logMessage = f"Request error: {req_error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
    except sqlite3.Error as sql_error:
        logMessage = f"SQLite error: {sql_error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
    except Exception as e:
        logMessage = f"An unexpected error occurred: {e}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
    finally:
        conn.close()
        logging.debug(f"Database connection closed for club {club['clubId']}")

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

    logging.info(f"Total Calendars loaded: {len(loadedCalendars)}")
    logging.info(f"Total Games loaded: {len(loadedGames)}")
    logging.info(f"Total Events loaded: {len(calendarEvents)}")

    for game in loadedGames:
        if game['teamCalendarId'] == None:
            calendar = checkCalendarExists(game['league'])
            if calendar != None:
                updateGameDB(game['id'], 'teamCalendarId', calendar['googleCalendarId'])
                game['teamCalendarId'] = calendar['googleCalendarId']
            else:
                logging.warning(f"Calendar for league {game['league']} not found")
                continue

        if game['date'] == None or game['date'] == '':
            logging.warning(f"Game with id {game['id']} has no date set. Unable to create a Calendar Event.")
            noDateGamesCount += 1
            continue

        if game['clubCalendarEventId'] == None:
            updateEvent(game, 'clubCalendarEventId', clubCalendarId, 'create')
            createdClubGamesCount += 1
            logging.debug(f"Created game with id {game['id']}")
        else:
            for event in calendarEvents:
                if (event['id'] == game['clubCalendarEventId']):
                    if not compareGame(game, event):
                        updateEvent(game, 'clubCalendarEventId', clubCalendarId, 'update')
                        updatedClubGamesCount += 1
                        logging.info(f"Updated game with id {game['id']} in Club-Calendar to date {game['date']}")
                    else:
                        unchangedClubGamesCount += 1
                    break

        if game['teamCalendarEventId'] == None:
            updateEvent(game, 'teamCalendarEventId', game['teamCalendarId'], 'create')
            createdTeamGamesCount += 1
            logging.debug(f"Created game with id {game['id']}")
        else:
            for event in calendarEvents:
                if (event['id'] == game['teamCalendarEventId']):
                    if not compareGame(game, event):
                        updateEvent(game, 'teamCalendarEventId', game['teamCalendarId'], 'update')
                        updatedTeamGamesCount += 1
                        logging.info(f"Updated game with id {game['id']} in Team-Calendar to date {game['date']}")
                    else:
                        unchangedTeamGamesCount += 1
                    break

    logMessages = [
        f"Games without date: {noDateGamesCount}",
        f"Created Club-Calendar Events: {createdClubGamesCount}",
        f"Updated Club-Calendar Events: {updatedClubGamesCount}",
        f"Unchanged Club-Calendar Events: {unchangedClubGamesCount}",
        f"Created Team-Calendar Events: {createdTeamGamesCount}",
        f"Updated Team-Calendar Events: {updatedTeamGamesCount}",
        f"Unchanged Team-Calendar Events: {unchangedTeamGamesCount}",
    ]

    notification = ''
    for message in logMessages:
        logging.info(message)
        notification += message + '\n'
    
    title = CLUBNAMESHORT + ": Gameplan Update"
    
    sendNotification(title, notification)

def loadGames():
    try:
        conn = sqlite3.connect(GAMEDBPATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT * FROM game
        ''')

        games = c.fetchall()
        games = [dict(game) for game in games]

        if (DEBUG):
            games = games[:2]

        conn.close()
        return games
    except sqlite3.Error as error:
        logMessage = f"An error occured: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        return []

def updateGameDB(id, field, value):
    try:
        conn = sqlite3.connect(GAMEDBPATH)
        c = conn.cursor()
        logging.debug(f"Attempting to update game with id {id}: Field {field} with value {value}")

        query = f'''
            UPDATE game
            SET {field} = :value
            WHERE id = :id
        '''
        c.execute(query, {'id': id, 'value': value})

        logging.debug(f"Rows updated: {c.rowcount}")

        conn.commit()
    except sqlite3.Error as error:
        logMessage = f"An error occured: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
    finally:
        conn.close()

def createGameTable(conn):
    c = conn.cursor()
    c.execute('''
        CREATE TABLE game (
            id text PRIMARY KEY,
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

#endregion

#region Calendars

def updateCalendars():
    leagues = findLeagues()
    createCalendarDB(None, True)

    for league in leagues:
        createCalendarDB(league['league'])

def createCalendarDB(league=None, isClubCalendar=False):
    if not os.path.exists(CALENDARDBPATH):
        try:
            conn = sqlite3.connect(CALENDARDBPATH)
            createCalendarTable(conn)
        except sqlite3.Error as error:
            logMessage = f"An error occured while creating Calendar Table: {error}"
            logging.error(logMessage)
            sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        finally:
            if conn:
                conn.close()

    if checkCalendarExists(league):
        return
    else:
        try:
            googleCalendarId = createGoogleCalendar(league)
            conn = sqlite3.connect(CALENDARDBPATH)
            c = conn.cursor()

            if (league == None):
                league = 'club'

            c.execute('''
                INSERT INTO calendar (id, googleCalendarId, league, isClubCalendar)
                VALUES (:id, :googleCalendarId, :league, :isClubCalendar)
            ''', {
                'id': league,
                'googleCalendarId': googleCalendarId,
                'league': league,
                'isClubCalendar': isClubCalendar
            })

            conn.commit()
        except sqlite3.Error as error:
            logMessage = f"An error occured: {error}"
            logging.error(logMessage)
            sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        finally:
            if conn:
                conn.close()

def loadCalendars():
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(f'''
            SELECT * FROM calendar
        ''')

        calendars = c.fetchall()
        calendars = [dict(calendar) for calendar in calendars]

        conn.close()
        return calendars
    except sqlite3.Error as error:
        logMessage = f"An error occured: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        return None

def loadCalendar(field, value):
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute(f'''
            SELECT * FROM calendar
            WHERE {field} = :value
        ''', {'value': value})

        calendar = c.fetchone()
        calendar = dict(calendar)

        conn.close()
        return calendar
    except sqlite3.Error as error:
        logMessage = f"An error occured: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        return None

def checkCalendarExists(league = None):
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        conn.row_factory = sqlite3.Row
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
    except sqlite3.Error as error:
        logMessage = f"An error occured: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        return None

def createCalendarTable(conn):
    c = conn.cursor()
    c.execute('''
        CREATE TABLE calendar (
            id text PRIMARY KEY,
            googleCalendarId text,
            league text NULL,
            isClubCalendar boolean
        )
    ''')

#endregion

#region Helper

def findLeagues():
    try:
        conn = sqlite3.connect(GAMEDBPATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT DISTINCT league FROM game
        ''')

        leagues = c.fetchall()
        leagues = [dict(league) for league in leagues]

        conn.close()
        return leagues
    except sqlite3.Error as error:
        logMessage = f"An error occured: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        return []

def compareGame(game, calendarEvent):
    game_date = parser.parse(game['date'])
    calendar_event_date = parser.parse(calendarEvent['start']['dateTime'])
    return (
        game_date == calendar_event_date and
        game['gym'] == calendarEvent['location']
    )

#endregion

#region Notification

def sendNotification(title, message):

    if GOTIFYURL == None or GOTIFYTOKEN == None:
        logging.warning("Gotify URL or Token not set. Skipping notification.")
        return

    # Payload for the notification
    payload = {
        "title": title,
        "message": message,
        "priority": 5
    }

    # Headers for the request
    headers = {
        "X-Gotify-Key": GOTIFYTOKEN
    }

    # Send the POST request to Gotify
    response = requests.post(GOTIFYURL, json=payload, headers=headers)

    # Check if the request was successful
    if response.status_code == 200:
        logging.info("Notification sent successfully!")
    else:
        logging.error(f"Failed to send notification: {response.status_code} - {response.text}")

#endregion

#region Logging

def logStartTime():
    global startTime
    startTime = time.time()
    logging.info("------------------------------------------------")
    logging.info(f"Start time: {time.ctime(startTime)}")

def logEndTime():
    endTime = time.time()
    duration = round(endTime - startTime, 1)
    logging.info(f"End time: {time.ctime(endTime)}")
    logging.info(f"Duration: {duration} seconds")
    logging.info("Ending script ------------------------------------------------")

def setupLogging():
    if not os.path.exists(LOGPATH):
        os.makedirs(LOGPATH)
    
    handler = TimedRotatingFileHandler(
        filename=os.path.join(LOGPATH, 'app.log'),
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8',
    )
    
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(funcName)s] - %(message)s')
    handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.setLevel(LOGLEVEL)
    logger.addHandler(handler)

#endregion

if __name__ == "__main__":
    main()