"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from audit_record_repository import AuditRecordRepository
from customer_repository import CustomerRepository
from database import Database
from models import Customer


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.audit_record_repo = AuditRecordRepository(db)
        self.customer_repo = CustomerRepository(db)

    def add_customer(self, first_name: str, last_name: str, email: str, phone: str) -> bool:
        customer = Customer(first_name=first_name, last_name=last_name, email=email, phone=phone, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.customer_repo.create(customer)

    def update_customer(self, id: int, first_name: str, last_name: str, email: str, phone: str) -> bool:
        data = {k: v for k, v in {'first_name': first_name, 'last_name': last_name, 'email': email, 'phone': phone}.items() if v is not None}
        return self.customer_repo.update(id, data)

    def delete_customer(self, id: int) -> bool:
        return self.customer_repo.delete(id)

    def list_customer(self, first_name: Optional[str] = None, last_name: Optional[str] = None, email: Optional[str] = None, created_at: Optional[str] = None, created_at_end: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.customer_repo.list(first_name=first_name, last_name=last_name, email=email, created_at=created_at, created_at_end=created_at_end)

