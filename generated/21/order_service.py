"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from customer_repository import CustomerRepository
from database import Database
from models import Customer
from order_repository import OrderRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.order_repo = OrderRepository(db)

    def add_customer(self, name: str, email: str) -> None:
        customer = Customer(name=name, email=email)
        return self.customer_repo.create(customer)

    def list_customer(self) -> List[Customer]:
        return self.customer_repo.list()

    def update_order(self, id: int, customer_id: int, order_date: Optional[str] = None, status: str = None) -> None:
        data = {k: v for k, v in {'customer_id': customer_id, 'order_date': order_date, 'status': status}.items() if v is not None}
        return self.order_repo.update(id, data)

    def delete_order(self, id: int) -> None:
        return self.order_repo.delete(id)

    def delete_customer(self, id: int) -> None:
        return self.customer_repo.delete(id)

