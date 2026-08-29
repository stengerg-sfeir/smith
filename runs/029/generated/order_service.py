"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    CustomerNotFoundError,
    OrderNotFoundError,
    ValidationError,
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
        """Retrieve orders with total amount within the specified range."""
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
        order = self.order_repo.get_order_by_id(order_id)
        if not order:
            raise OrderNotFoundError(f'Order with id {order_id} not found')
        customer = self.customer_repo.get_by_id(order.customer_id)
        if not customer:
            raise CustomerNotFoundError(f'Customer with id {order.customer_id} not found')
        return {order: customer}

    def get_order_with_most_spent(self) -> Optional[Order]:
        """Returns the order with the highest total amount, or None if no orders exist."""
        return self.order_repo.get_order_with_most_spent()

    def get_orders_by_customer(self, customer_id: int, status: Optional[str]=None, from_date: Optional[datetime.datetime]=None, to_date: Optional[datetime.datetime]=None) -> List[Order]:
        """
            Retrieves orders for a specific customer with optional filters on status, date range.
        
            Args:
                customer_id: ID of the customer to get orders for
                status: Optional status filter (e.g., 'pending', 'shipped')
                from_date: Optional start date (inclusive)
                to_date: Optional end date (inclusive)
        
            Returns:
                List of Order objects matching the criteria
            """
        return self.order_repo.get_orders_by_customer(customer_id, status, from_date, to_date)

    def get_orders_in_month(self, year_month: str) -> List[Order]:
        try:
            year, month = map(int, year_month.split('-'))
            start_date = datetime.date(year, month, 1)
            if month == 12:
                end_date = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
            else:
                end_date = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
            orders = self.order_repo.get_orders_in_date_range(start_date, end_date)
            return orders
        except Exception as e:
            raise ValidationError(f'Invalid date format or parsing error: {str(e)}')

    def get_orders_below_customer_threshold(self, customer_id: int, threshold_amount: float) -> List[Order]:
        customer = self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise CustomerNotFoundError(f'Customer with id {customer_id} not found')
        orders = self.order_repo.get_orders_by_customer(customer_id=customer_id, status=None, from_date=None, to_date=None)
        filtered_orders = [order for order in orders if order.total_amount < threshold_amount]
        return filtered_orders

