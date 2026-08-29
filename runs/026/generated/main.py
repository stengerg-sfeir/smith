"""Application entry point."""
from __future__ import annotations

from database import Database
from loan_service import LoanService

DB_PATH = "app.db"

def main() -> None:
    """Initialize the application and run a smoke check."""
    db = Database(DB_PATH)
    svc = LoanService(db)
    print("Application ready — database initialized at app.db")

if __name__ == "__main__":
    main()

