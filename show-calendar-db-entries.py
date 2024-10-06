import sys
import os
import sqlite3
from pprint import pprint

# Add the parent directory to sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

from config import CALENDARDBPATH


def loadCalendars():
    try:
        conn = sqlite3.connect(CALENDARDBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT * FROM calendar
        ''')

        calendars = c.fetchall()

        # Convert sqlite3.Row objects to dictionaries
        calendars = [dict(calendar) for calendar in calendars]

        conn.close()
        return calendars
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")

pprint(loadCalendars(), indent=4)