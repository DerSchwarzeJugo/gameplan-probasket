import sqlite3

DBPATH = './data/games.db'
DEBUG = True

def loadGames():
    try:
        conn = sqlite3.connect(DBPATH)
        conn.row_factory = sqlite3.Row  # Set row factory to sqlite3.Row
        c = conn.cursor()

        c.execute('''
            SELECT * FROM games
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
        print(f"An error occurred: {e}")

print(loadGames())