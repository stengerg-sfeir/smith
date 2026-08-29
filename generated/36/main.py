"""Application entry point."""
from __future__ import annotations

from database import Database
from product_service import ProductService

DB_PATH = "app.db"

def main() -> None:
    """Initialize the application and run a smoke check."""
    db = Database(DB_PATH)
    svc = ProductService(db)
    print("Application ready — database initialized at app.db")

if __name__ == "__main__":
    main()

