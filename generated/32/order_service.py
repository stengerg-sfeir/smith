"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from exceptions import (
    InvalidStateTransitionError,
    OrderAlreadyCancelledError,
    OrderAlreadyShippedError,
    OrderNotFoundError,
)
from models import Order
from order_repository import OrderRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)

    def create_order(self, customer_id: int, total_amount: float) -> Order:
        """Create a new order with the given customer ID and total amount."""
        order = Order(created_at=datetime.datetime.now(), customer_id=customer_id, id=None, status='pending', total_amount=total_amount, updated_at=datetime.datetime.now())
        return self.order_repo.create(order)

    def get_order_by_customer_and_status(self, customer_id: int, status: str) -> Optional[Order]:
        """Retrieve an order by customer ID and status."""
        return self.order_repo.get_order_by_customer_and_status(customer_id, status)

    def get_orders_by_status_and_date_range(self, status: str, start_date: datetime.datetime, end_date: datetime.datetime) -> list[Order]:
        """Retrieve orders by status and date range."""
        return self.order_repo.get_orders_by_status_and_date_range(status, start_date, end_date)

    def get_total_orders_by_status(self) -> dict[str, int]:
        """Get total count of orders grouped by status."""
        return self.order_repo.get_total_orders_by_status()

    def get_pending_orders_count(self) -> int:
        """Get the count of pending orders."""
        return self.order_repo.get_pending_orders_count()

    def get_confirmed_orders_count(self) -> int:
        """Get the count of confirmed orders."""
        return self.order_repo.get_confirmed_orders_count()

    def get_shipped_orders_count(self) -> int:
        """Get the count of shipped orders."""
        return self.order_repo.get_shipped_orders_count()

    def get_cancelled_orders_count(self) -> int:
        """Get the count of cancelled orders."""
        return self.order_repo.get_cancelled_orders_count()

    def get_orders_with_latest_status_change(self) -> list[Order]:
        """Get orders with the most recent status change."""
        return self.order_repo.get_orders_with_latest_status_change()

    def get_orders_with_total_amount_range(self, min_amount: float, max_amount: float) -> list[Order]:
        """Get orders within a total amount range."""
        return self.order_repo.get_orders_with_total_amount_range(min_amount, max_amount)

    def update_order_status(self, order_id: int, new_status: str) -> None:
        """Update the status of an order, ensuring valid state transitions."""
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise OrderNotFoundError(f'Order with id {order_id} not found')
        valid_transitions = {'pending': ['confirmed', 'cancelled'], 'confirmed': ['shipped', 'cancelled'], 'shipped': ['cancelled'], 'cancelled': []}
        if order.status not in valid_transitions or new_status not in valid_transitions[order.status]:
            raise InvalidStateTransitionError(f'Invalid state transition from {order.status} to {new_status}')
        if new_status == 'cancelled':
            if order.status in ['shipped']:
                raise OrderAlreadyShippedError(f'Order {order_id} is already shipped and cannot be cancelled')
            if order.status in ['cancelled']:
                raise OrderAlreadyCancelledError(f'Order {order_id} is already cancelled')
        if new_status == 'shipped':
            if order.status != 'confirmed':
                raise InvalidStateTransitionError(f'Order {order_id} must be confirmed before shipping')
        order.status = new_status
        order.updated_at = datetime.datetime.now()
        self.order_repo.update(order.id, {'status': new_status, 'updated_at': order.updated_at})

