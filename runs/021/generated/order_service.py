"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    CustomerNotFoundError,
    InvalidOrderStatusError,
    OrderNotFoundError,
)
from models import Order
from order_repository import OrderRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.order_repo = OrderRepository(db)

    def create_order(self, customer_id: int, order_date: datetime, status: str) -> bool:
        if customer_id is not None:
            if self.customer_repo.get_by_id(customer_id) is None:
                raise CustomerNotFoundError(customer_id)
        order = Order(customer_id=customer_id, order_date=order_date, status=status)
        return self.order_repo.create(order)

    def get_customer_orders(self, customer_id: int, status: Optional[str]=None, start_date: Optional[datetime]=None, end_date: Optional[datetime]=None) -> List[Order]:
        """
            Retrieve customer orders with optional filtering by status and date range.
            """
        orders: List[Order] = []
        if status is not None:
            orders = self.customer_repo.get_customer_orders_with_status_filter(customer_id, status)
        else:
            orders = self.customer_repo.get_customer_orders_with_date_range(customer_id, start_date, end_date)
        if start_date is not None or end_date is not None:
            filtered_orders = []
            for order in orders:
                order_date = order.order_date
                if start_date and order_date < start_date:
                    continue
                if end_date and order_date > end_date:
                    continue
                filtered_orders.append(order)
            orders = filtered_orders
        return orders

    def get_customer_order_count_by_status(self, customer_id: int) -> Dict[str, int]:
        rows = self.order_repo.list(customer_id=customer_id)
        total = sum(e.status for e in rows)
        return {'order_count_by_status': total}

    def get_customer_total_orders_and_revenue(self, customer_id: int) -> Dict[str, Any]:
        results = {}
        for row in self.order_repo.list(customer_id=customer_id):
            key = row.status
            results[key] = results.get(key, 0) + row.order_date
        return results

    def update_order_status(self, order_id: int, new_status: str) -> bool:
        """
            Update the status of an order.
            Returns True if successful, False otherwise.
            """
        try:
            valid_statuses = ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
            if new_status not in valid_statuses:
                raise InvalidOrderStatusError(f'Invalid status: {new_status}. Must be one of {valid_statuses}')
            order = self.order_repo.get_by_id(order_id)
            if not order:
                raise OrderNotFoundError(f'Order with ID {order_id} not found')
            order.status = new_status
            self.order_repo.update(order_id, {'status': new_status})
            return True
        except Exception as e:
            raise e

    def export_orders_to_csv(self, customer_id: int, file_path: str) -> None:
        rows = self.order_repo.list(customer_id=customer_id, )
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'customer_id', 'order_date', 'status',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.customer_id, row.order_date, row.status,
                ])

    def get_orders_by_status_and_date_range(self, status: str, start_date: datetime, end_date: datetime) -> List[Order]:
        """
            Retrieve orders by status and date range.
            """
        return self.order_repo.get_orders_by_status_and_date_range(status, start_date, end_date)

