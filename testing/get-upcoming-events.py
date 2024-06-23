import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

def main():
    creds = None
    if os.path.exists("token.json"):
      creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
      if creds and creds.expired and creds.refresh_token:
        try:
          creds.refresh(Request())
        except Exception as e:
          print(f"Error refreshing access token: {e}")
          creds = None
      if not creds:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
      with open("token.json", "w") as token:
        token.write(creds.to_json())

    try:
      service = build("calendar", "v3", credentials=creds)
      now = datetime.datetime.utcnow().isoformat() + "Z"
      print("Getting the upcoming 10 events")
      # The calendar ID can be found in the settings of the Google Calendar (this is the id of the EB calendar)
      calendar_id = "925a0d61e624b1742abf37419fb1ff0777c5b40cb1166d8be0c6b42d7f6432a2@group.calendar.google.com"
      events_result = service.events().list(calendarId=calendar_id, timeMin=now, maxResults=10, singleEvents=True, orderBy="startTime").execute()
      events = events_result.get("items", [])

      if not events:
        print("No upcoming events found.")
        return

      for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        print(start, event["summary"])

    except HttpError as error:
      print(f"An error occurred: {error}")

if __name__ == "__main__":
    main()