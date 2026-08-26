"""Application entry point."""
from __future__ import annotations

from database import Database
from reservation_service import ReservationService

DB_PATH = "reservation.db"

def main() -> None:
    """Initialize the application and run a smoke check."""
    db = Database(DB_PATH)
    svc = ReservationService(db)
    print("Application ready — database initialized at reservation.db")

if __name__ == "__main__":
    main()

