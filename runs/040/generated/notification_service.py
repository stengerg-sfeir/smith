"""Service layer."""
from __future__ import annotations

import datetime

from database import Database
from exceptions import NotFoundError
from models import Notification, Order
from order_repository import OrderRepository


class NotificationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)

    def send_notification(self, order_id: int, message: str, sent_to: str) -> None:
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        notification = Notification(id=None, message=message, order_id=order_id, sent_at=datetime.datetime.now(), sent_to=sent_to)
        self.order_repo.update(order_id, {'status': 'notified'})
        self.log_notification(order_id, message, sent_to)

    def send_confirmation_notification(self, order: Order) -> None:
        if not order:
            raise NotFoundError('Order not found')
        message = f'Thank you for your order! Your order #{order.id} is confirmed.'
        self.send_notification(order.id, message, order.customer_id)

    def log_notification(self, order_id: int, message: str, sent_to: str) -> None:
        print(f'Notification logged: Order {order_id}, Message: {message}, Sent to: {sent_to}')

