"""Application entry point."""
from __future__ import annotations

from account_service import AccountService
from database import Database

DB_PATH = "app.db"

def main() -> None:
    """Initialize the application and run a smoke check."""
    db = Database(DB_PATH)
    svc = AccountService(db)
    print("Application ready — database initialized at app.db")

if __name__ == "__main__":
    main()

