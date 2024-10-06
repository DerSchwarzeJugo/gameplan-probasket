from script import authenticate, getGoogleService, setupLogging
import logging


def main():
    setupLogging()
    authenticate()
    listGoogleCalendars()

def listGoogleCalendars():
    service = getGoogleService()
    page_token = None
    while True:
        calendarList = service.calendarList().list(pageToken=page_token).execute()

        if (len(calendarList['items']) == 0):
            logging.info("No calendars found.")

        for cal in calendarList['items']:
            logging.info(f"Calendar ID: {cal['id']}, Summary: {cal['summary']}")
        page_token = calendarList.get('nextPageToken')
        if not page_token:
            break

if __name__ == "__main__":
    main()