"""Service layer."""
from __future__ import annotations

import csv
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

    def create_order(self, customer_id: int, order_date: datetime, total_amount: float, status: str) -> bool:
        if customer_id is not None:
            if self.customer_repo.get_by_id(customer_id) is None:
                raise CustomerNotFoundError(customer_id)
        order = Order(customer_id=customer_id, order_date=order_date, total_amount=total_amount, status=status, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.order_repo.create(order)

    def get_order_by_id(self, order_id: int) -> Optional[Order]:
        return self.order_repo.get_by_id(order_id)

    def get_orders_by_status(self, status: str, from_date: Optional[datetime]=None, to_date: Optional[datetime]=None) -> List[Order]:
        return self.order_repo.get_orders_by_status(status, from_date, to_date)

    def get_orders_in_date_range(self, from_date: datetime, to_date: datetime) -> List[Order]:
        return self.order_repo.get_orders_in_date_range(from_date, to_date)

    def get_orders_by_total_range(self, min_amount: float, max_amount: float) -> List[Order]:
        return self.order_repo.get_orders_by_total_range(min_amount, max_amount)

    def get_order_summary_by_status(self) -> Dict[str, float]:
        return self.order_repo.get_order_summary_by_status()

    def get_active_orders_count(self) -> int:
        return self.order_repo.get_active_orders_count()

    def export_orders_to_csv(self, file_path: str) -> None:
        rows = self.order_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'customer_id', 'order_date', 'total_amount',
                'status', 'created_at', 'updated_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.customer_id, row.order_date, row.total_amount,
                    row.status, row.created_at, row.updated_at,
                ])

    def get_orders_with_customer_details(self, order_id: int) -> Dict[Order, Customer]:
        return self.order_repo.get_orders_with_customer_details(order_id)

    def get_order_with_most_spent(self) -> Optional[Order]:
        return self.order_repo.get_order_with_most_spent()

    def get_orders_by_customer(self, customer_id: int, status: Optional[str]=None, from_date: Optional[datetime]=None, to_date: Optional[datetime]=None) -> List[Order]:
        return self.order_repo.get_orders_by_customer(customer_id, status, from_date, to_date)

    def get_orders_in_month(self, year_month: str) -> List[Order]:
        raise NotImplementedError()

    def get_orders_below_customer_threshold(self, customer_id: int, threshold_amount: float) -> List[Order]:
        raise NotImplementedError()

