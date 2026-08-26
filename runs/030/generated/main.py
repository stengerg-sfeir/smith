"""Application entry point."""
from __future__ import annotations

import sqlite3


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

def main() -> None:
    """Initialize the application and run a smoke check."""
    db = Database(DB_PATH)
    try:
        # Simple smoke test: check if connection is valid
        cursor = db.conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        print("Application ready — database initialized at app.db")
    except Exception as e:
        print(f"Error during database initialization: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
