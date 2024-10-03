import sys
import os
import sqlite3
from pprint import pprint

# Add the parent directory to sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)

from config import DEBUG, GAMEDBPATH


def loadGames():
    try:
        conn = sqlite3.connect(GAMEDBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT * FROM game
            Order by date
        ''')

        games = c.fetchall()

        # Convert sqlite3.Row objects to dictionaries
        games = [dict(game) for game in games]

        if (DEBUG):
            # trim to 2 games only for testing
            games = games[:2]

        conn.close()
        print(f"Loaded {len(games)} games from the database.")
        return games
    except sqlite3.Error as e:
        print(f"An error occurred: {e}")

pprint(loadGames(), indent=4)