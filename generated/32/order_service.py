"""Service layer."""
from __future__ import annotations

import datetime

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

    def add_order(self, customer_id: int, status: str, total_amount: str) -> bool:
        order = Order(customer_id=customer_id, status=status, total_amount=total_amount, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.order_repo.create(order)

    def confirm_order(self, id: int) -> bool:
        order = self.order_repo.get_by_id(id)
        if not order:
            raise OrderNotFoundError(f'Order with id {id} not found')
        if order.status == 'confirmed':
            return False
        if order.status == 'cancelled':
            raise InvalidStateTransitionError('Cannot confirm a cancelled order')
        if order.status == 'shipped':
            raise InvalidStateTransitionError('Cannot confirm a shipped order')
        self.order_repo.update(id, {'status': 'confirmed'})
        return True

    def ship_order(self, id: int) -> bool:
        order = self.order_repo.get_by_id(id)
        if not order:
            raise OrderNotFoundError(f'Order with id {id} not found')
        if order.status == 'shipped':
            raise OrderAlreadyShippedError(f'Order with id {id} is already shipped')
        if order.status == 'cancelled':
            raise InvalidStateTransitionError('Cannot ship a cancelled order')
        if order.status == 'confirmed':
            self.order_repo.update(id, {'status': 'shipped'})
            return True
        raise InvalidStateTransitionError('Order must be confirmed before shipping')

    def cancel_order(self, id: int) -> bool:
        order = self.order_repo.get_by_id(id)
        if not order:
            raise OrderNotFoundError(f'Order with id {id} not found')
        if order.status == 'cancelled':
            raise OrderAlreadyCancelledError(f'Order with id {id} is already cancelled')
        if order.status == 'shipped':
            raise InvalidStateTransitionError('Cannot cancel a shipped order')
        self.order_repo.update(id, {'status': 'cancelled'})
        return True

    def check_order(self, id: int) -> dict[str, any]:
        order = self.order_repo.get_by_id(id)
        if not order:
            raise OrderNotFoundError(f'Order with id {id} not found')
        status_history = self.order_repo.get_orders_with_status_history(id)
        return {'id': order.id, 'customer_id': order.customer_id, 'status': order.status, 'total_amount': order.total_amount, 'created_at': order.created_at, 'updated_at': order.updated_at, 'status_history': status_history}

