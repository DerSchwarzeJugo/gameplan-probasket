from config import DEBUG, LOGLEVEL, LOGPATH, SCOPES, GAMEDBPATH, CALENDARDBPATH, PROBASKETCLUBS, CLUBNAME, CLUBNAMESHORT, CLUBGAMESURL, GOTIFYURL, GOTIFYTOKEN, SERVICEACCOUNTFILE, PERSONALEMAIL
import time
import datetime
import pytz
import locale
import os.path
import requests
from bs4 import BeautifulSoup
import os
import uuid
import sqlite3
import logging
from logging.handlers import TimedRotatingFileHandler
from dateutil import parser

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account

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
    try:
        # Load the service account credentials
        creds = service_account.Credentials.from_service_account_file(
            SERVICEACCOUNTFILE, scopes=SCOPES)
        
        # Refresh the token if necessary
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
    except Exception as e:
        logMessage = f"Error with service account authentication: {e}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)
        creds = None
    
    return creds

def getGoogleService():
    creds = authenticate()
    if creds:
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        return service
    return None

def createGoogleCalendar(league=None):
    try:
        service = getGoogleService()
        if league is not None:
            calendarName = CLUBNAMESHORT + ' ' + league
        else:
            calendarName = CLUBNAME

        calendar = {
            'summary': calendarName,
            'timeZone': 'Europe/Zurich'
        }

        created_calendar = service.calendars().insert(body=calendar).execute()

        # Make the calendar publicly accessible
        rule = {
            'scope': {
                'type': 'default',
            },
            'role': 'reader'
        }
        service.acl().insert(calendarId=created_calendar['id'], body=rule).execute()

        return created_calendar['id']
    except HttpError as error:
        logMessage = f"An error occurred: {error}"
        logging.error(logMessage)
        sendNotification(CLUBNAMESHORT + ": Gameplan Error", logMessage)

def fetchEvents(calendar):
    try:
        service = getGoogleService()
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

def bulkUpdateEvents(games, case='update', clubCalendarId=None):
    service = getGoogleService()
    batch = service.new_batch_http_request()

    results = []
    gameMap = {}

    def callback(request_id, response, exception):
        if exception is not None:
            results.append({'request_id': request_id, 'status': 'failed', 'error': str(exception)})
        else:
            event_id = response.get('id') if response else None
            results.append({'request_id': request_id, 'status': 'success', 'response': response, 'event_id': event_id})
            # Update the game in the database with the new event ID
            game = gameMap[request_id]
            field = 'teamCalendarEventId' if clubCalendarId is None else 'clubCalendarEventId'
            updateGameDB(game['id'], field, event_id)

    for game in games:
        startDateTime = parser.parse(game['date'])
        zurich_tz = pytz.timezone('Europe/Zurich')
        startDateTime = startDateTime.astimezone(zurich_tz)
        endDateTime = startDateTime + datetime.timedelta(hours=2)

        event = {
            'summary': f'{game["league"]} {game["homeTeam"]} vs. {game["awayTeam"]}',
            'location': game['gym'],
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

        # Generate a unique request_id for each game
        request_id = str(uuid.uuid4())
        gameMap[request_id] = game

        if case == 'update':
            if clubCalendarId is None:
                batch.add(service.events().patch(calendarId=game['teamCalendarId'], eventId=game['teamCalendarEventId'], body=event), callback=callback, request_id=request_id)
            else:
                batch.add(service.events().patch(calendarId=clubCalendarId, eventId=game['clubCalendarEventId'], body=event), callback=callback, request_id=request_id)
        elif case == 'create':
            if clubCalendarId is None:
                batch.add(service.events().insert(calendarId=game['teamCalendarId'], body=event), callback=callback, request_id=request_id)
            else:
                batch.add(service.events().insert(calendarId=clubCalendarId, body=event), callback=callback, request_id=request_id)

    batch.execute()
    return results

def updateGameDB(game_id, field, event_id):
    # Implement the logic to update the game in the database with the new event ID
    # Example: Update the database with the new event ID
    # db.update_game(game_id, {field: event_id})
    pass

def fetchCalendarEvents(loadedCalendars):
    allEvents = []
    for calendar in loadedCalendars:
        events = fetchEvents(calendar)
        if events != None:
            allEvents.extend(events)

    return allEvents

def shareCalendars():
    creds = authenticate()
    if creds:
        service = build('calendar', 'v3', credentials=creds)
        try:
            calendar_list = service.calendarList().list().execute()
            calendars = calendar_list.get('items', [])
            for calendar in calendars:
                dbCalendar = loadCalendar('googleCalendarId', calendar['id'])

                if dbCalendar == None:
                    logging.warning(f"Calendar ID: {calendar['id']} not found in database")
                    continue

                if dbCalendar['isShared'] == 1:
                    logging.debug(f"Calendar ID: {calendar['id']} already shared")
                    continue

                calendar_id = calendar['id']
                
                rule = {
                    'scope': {
                        'type': 'user',
                        'value': PERSONALEMAIL,
                    },
                    'role': 'owner'
                }
                
                service.acl().insert(calendarId=calendar_id, body=rule).execute()
                logging.info(f"Shared calendar ID: {calendar_id} with {PERSONALEMAIL}")
                updateCalendarDBByGoogleId(calendar_id, 'isShared', 1)
        except Exception as e:
            logging.error(f"An error occurred: {e}")

def bulkDeleteCalendarEvents(games, clubCalendarId):
    service = getGoogleService()
    batch = service.new_batch_http_request()

    results = []

    def callback(request_id, response, exception):
        if exception is not None:
            results.append({'request_id': request_id, 'status': 'failed', 'error': str(exception)})
        else:
            results.append({'request_id': request_id, 'status': 'success', 'response': response})

    for game in games:
        batch.add(service.events().delete(calendarId=game['teamCalendarId'], eventId=game['teamCalendarEventId']), callback=callback)
        batch.add(service.events().delete(calendarId=clubCalendarId, eventId=game['clubCalendarEventId']), callback=callback)

    batch.execute()
    return results

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

                if club['combineLeagues'] != None:
                    for combine in club['combineLeagues']:
                        if league == combine['combine']:
                            league = combine['into']

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

    clubGamesToCreate = []
    clubGamesToUpdate = []
    teamGamesToCreate = []
    teamGamesToUpdate = []
    gamesToDelete = []

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
            logging.warning(f"Game with id {game['id']} has no date set. Unable to create or update a Calendar Event.")
            noDateGamesCount += 1
            gamesToDelete.append(game)
            continue

        if game['clubCalendarEventId'] == None:
            clubGamesToCreate.append(game)
        else:
            for event in calendarEvents:
                if event['id'] == game['clubCalendarEventId']:
                    if not compareGame(game, event):
                        clubGamesToUpdate.append(game)
                    else:
                        unchangedClubGamesCount += 1
                    break

        if game['teamCalendarEventId'] == None:
            teamGamesToCreate.append(game)
        else:
            for event in calendarEvents:
                if event['id'] == game['teamCalendarEventId']:
                    if not compareGame(game, event):
                        teamGamesToUpdate.append(game)
                    else:
                        unchangedTeamGamesCount += 1
                    break

    # Bulk update club calendar events
    clubCreateResults = bulkUpdateEvents(clubGamesToCreate, 'create', clubCalendarId)
    clubUpdateResults = bulkUpdateEvents(clubGamesToUpdate, 'update', clubCalendarId)

    # Bulk update team calendar events
    teamCreateResults = bulkUpdateEvents(teamGamesToCreate, 'create')
    teamUpdateResults = bulkUpdateEvents(teamGamesToUpdate, 'update')

    # Bulk delete calendar events
    deleteResults = bulkDeleteCalendarEvents(gamesToDelete, clubCalendarId)

    # Update counters based on results
    createdClubGamesCount += len(clubCreateResults)
    updatedClubGamesCount += len(clubUpdateResults)
    createdTeamGamesCount += len(teamCreateResults)
    updatedTeamGamesCount += len(teamUpdateResults)
    deletedGamesCount = len(deleteResults)

    logMessages = [
        f"Games without date: {noDateGamesCount}",
        f"Deleted Games: {deletedGamesCount}",
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

    shareCalendars()

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
            isClubCalendar boolean,
            isShared boolean DEFAULT 0
        )
    ''')

def updateCalendarDBByGoogleId(id, field, value):
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        c = conn.cursor()
        logging.debug(f"Attempting to update calendar with Google CalendarID {id}: Field {field} with value {value}")

        query = f'''
            UPDATE calendar
            SET {field} = :value
            WHERE googleCalendarId = :id
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
    gameDate = parser.parse(game['date'])
    calendarEventDate = parser.parse(calendarEvent['start']['dateTime'])
    
    return (
        gameDate == calendarEventDate and
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
        logging.debug("Notification sent successfully!")
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