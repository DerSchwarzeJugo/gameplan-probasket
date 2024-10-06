from config import CALENDARDBPATH
from script import authenticate, getGoogleService, loadCalendar, setupLogging
import sqlite3
import logging


def main():
    setupLogging()
    authenticate()
    deleteGoogleCalendars()


def deleteGoogleCalendars():
    service = getGoogleService()
    page_token = None
    while True:
        calendarList = service.calendarList().list(pageToken=page_token).execute()
        for cal in calendarList['items']:
            service.calendars().delete(calendarId=cal['id']).execute()

            if loadCalendar('googleCalendarId', cal['id']) != None:
                deleteCalendarFromDatabase(cal['id'])

        page_token = calendarList.get('nextPageToken')
        if not page_token:
            break

def deleteCalendarFromDatabase(googleCalendarId):
    # Delete from database
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        c = conn.cursor()
        logging.debug(f"Attempting to delete calendar with Google CalendarID {googleCalendarId} from DB.")

        query = f'''
            DELETE FROM calendars
            WHERE googleCalendarId = ?
        '''
        c.execute(query, (googleCalendarId))

        logging.debug(f"Rows updated: {c.rowcount}")

        conn.commit()
    except sqlite3.Error as error:
        logMessage = f"An error occured: {error}"
        logging.error(logMessage)
    finally:
        conn.close()

if __name__ == "__main__":
    main()