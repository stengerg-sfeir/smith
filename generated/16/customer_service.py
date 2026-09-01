"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from customer_repository import CustomerRepository
from database import Database
from models import Customer


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)

    def add_customer(self, first_name: str, last_name: str, email: str, phone: str) -> bool:
        customer = Customer(first_name=first_name, last_name=last_name, email=email, phone=phone, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.customer_repo.create(customer)

    def list_customer(self, first_name: Optional[str] = None, last_name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None) -> list[Customer] & dict[str, int]:
        results = {}
        for row in self.customer_repo.list(first_name=first_name, last_name=last_name, email=email, phone=phone):
            key = (row.first_name, row.last_name)
            results[key] = results.get(key, 0) + row.id
        return results

    def update_customer(self, id: int, first_name: Optional[str] = None, last_name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'first_name': first_name, 'last_name': last_name, 'email': email, 'phone': phone}.items() if v is not None}
        return self.customer_repo.update(id, data)

    def delete_customer(self, id: int) -> bool:
        return self.customer_repo.delete(id)

