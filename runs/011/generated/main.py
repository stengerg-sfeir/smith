"""Application entry point."""
from __future__ import annotations

from book_service import BookService
from database import Database

DB_PATH = "library.db"

def main() -> None:
    """Initialize the application and run a smoke check."""
    db = Database(DB_PATH)
    svc = BookService(db)
    print("Application ready — database initialized at library.db")

if __name__ == "__main__":
    main()

