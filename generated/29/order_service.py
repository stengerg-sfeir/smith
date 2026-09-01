"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from customer_repository import CustomerRepository
from database import Database
from models import Customer
from order_repository import OrderRepository


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.order_repo = OrderRepository(db)

    def add_customer(self, name: str, email: str, phone: str) -> None:
        customer = Customer(name=name, email=email, phone=phone, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.customer_repo.create(customer)

    def list_customer(self) -> list[dict]:
        return self.customer_repo.list()

    def update_customer(self, id: int, name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None) -> None:
        data = {k: v for k, v in {'name': name, 'email': email, 'phone': phone}.items() if v is not None}
        return self.customer_repo.update(id, data)

    def delete_customer(self, id: int) -> None:
        return self.customer_repo.delete(id)

    def list_order(self, customer_id: str, status: Optional[str] = None) -> list[dict]:
        return self.order_repo.list(customer_id=customer_id, status=status)

    def update_order(self, id: int, customer_id: int, total_amount: str, status: str) -> None:
        data = {k: v for k, v in {'customer_id': customer_id, 'total_amount': total_amount, 'status': status}.items() if v is not None}
        return self.order_repo.update(id, data)

    def delete_order(self, id: int) -> None:
        return self.order_repo.delete(id)

