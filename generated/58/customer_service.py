"""Service layer."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)

    def list_customer(self, name: Optional[str] = None, email: Optional[str] = None, created_at: Optional[str] = None, created_at_end: Optional[str] = None) -> List[Dict[str, Any]]:
        rows = self.customer_repo.list(name=name, email=email, created_at=created_at, created_at_end=created_at_end)
        total = sum(e.created_at for e in rows)
        return {'total_customers': total}

