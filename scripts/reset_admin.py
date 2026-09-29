"""Offline administrator reset. Keep the server stopped while running this explicit operation."""
from pathlib import Path
import argparse
import sqlite3


def main():
    parser=argparse.ArgumentParser(description='Offline admin reset: stop the server and back up data first.')
    parser.add_argument('--data-dir',type=Path,required=True)
    args=parser.parse_args()
    db=args.data_dir/'library.sqlite3'
    if not db.is_file():raise SystemExit('Database not found; nothing changed.')
    with sqlite3.connect(db,timeout=1) as connection:
        connection.execute('BEGIN EXCLUSIVE')
        connection.execute("DELETE FROM settings WHERE key='password'")
        connection.execute('DELETE FROM sessions')
    print('Administrator reset. Start the server and use its newly generated setup-code.txt. Index preserved.')


if __name__=='__main__':main()
