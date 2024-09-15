# Description:
This script is used to update the Google Calendar with the latest basketball games from the ProBasket website for a provided club ID.

The script will create a new event for each game in the Club-Calendar and also a dedicated Team-Calendar. The script will update the events if the game data has changed.

The script will take care of creating new Team-Calendars automatically if necessary.

For a new season, just delete/archive the game.db and allow for a new one to be created. The calendar.db can be left in place, in order to spare some time of creating new calendars. Furthermore, the people using a calendar already, will not have to subscribe to a new calendar every season.