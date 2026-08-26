"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    CustomerNotFoundError,
)
from models import Customer, Order
from order_repository import OrderRepository


class CustomerService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.order_repo = OrderRepository(db)

    def create_customer(self, name: str, email: str, phone: Optional[str] = None) -> bool:
        customer = Customer(name=name, email=email, phone=phone, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.customer_repo.create(customer)

    def get_customer_by_email(self, email: str) -> Optional[Customer]:
        return self.customer_repo.get_customer_by_email(email)

    def get_customer_orders(self, customer_id: int, status: Optional[str]=None, from_date: Optional[datetime.datetime]=None, to_date: Optional[datetime.datetime]=None) -> List[Order]:
        return self.customer_repo.get_customer_orders(customer_id, status, from_date, to_date)

    def get_customer_with_orders(self, customer_id: int) -> Dict[Customer, List[Order]]:
        results = []
        groups = {}
        for row in self.order_repo.list(customer_id=customer_id):
            key = (row.status)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'status': key[0],
                    'count': len(group),
                })
        return results

    def get_active_customers_count(self) -> int:
        return self.customer_repo.get_active_customers_count()

    def get_customers_by_name_prefix(self, prefix: str) -> List[Customer]:
        return self.customer_repo.get_customers_by_name_prefix(prefix)

    def get_customer_total_spent(self, customer_id: int) -> float:
        rows = self.order_repo.list(
            order_date=str(customer_id) + '-01-01',
            order_date_end=str(customer_id) + '-12-31',
        )
        return sum(e.total_amount for e in rows)

    def get_customer_order_summary(self, customer_id: int) -> Dict[str, float]:
        results = {}
        for row in self.order_repo.list(customer_id=customer_id):
            key = row.status
            results[key] = results.get(key, 0) + row.total_amount
        return results

    def update_customer_phone(self, customer_id: int, phone: str) -> bool:
        try:
            customer = self.customer_repo.get_by_id(customer_id)
            if not customer:
                raise CustomerNotFoundError(f'Customer with id {customer_id} not found')
            updated_data = {'phone': phone}
            self.customer_repo.update(customer_id, updated_data)
            return True
        except Exception as e:
            raise e

