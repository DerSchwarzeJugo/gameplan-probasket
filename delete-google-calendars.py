from config import CALENDARDBPATH
from script import authenticate, getGoogleService, setupLogging
import sqlite3
import logging


def main():
    setupLogging()
    authenticate()
    # Prompt the user for confirmation
    confirmation = input("Are you sure you want to delete all Google calendars? This is not reversible!\nType 'yes' to confirm: ")
    
    # Check the user's response
    if confirmation.lower() == 'yes':
        calCount = deleteGoogleCalendars()
        logMessage = f"Deleted {calCount} calendars."
        print(logMessage)
        logging.info(logMessage)
    else:
        logMessage = "Operation cancelled. No calendars were deleted."
        print(logMessage)
        logging.info(logMessage)


def deleteGoogleCalendars():
    service = getGoogleService()
    pageToken = None
    deletedCalendars = 0

    while True:
        calendarList = service.calendarList().list(pageToken=pageToken).execute()

        if (len(calendarList['items']) == 0):
            logging.info("No calendars found.")

        for cal in calendarList['items']:
            service.calendars().delete(calendarId=cal['id']).execute()
            deleteCalendarFromDatabase(cal['id'])
            deletedCalendars += 1

        pageToken = calendarList.get('nextPageToken')
        if not pageToken:
            break
    
    return deletedCalendars

def deleteCalendarFromDatabase(googleCalendarId):
    # Delete from database
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        c = conn.cursor()
        logging.debug(f"Attempting to delete calendar with Google CalendarID {googleCalendarId} from DB.")

        # If the calendar is not in the database, nothing will happen
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