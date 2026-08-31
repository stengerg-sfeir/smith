"""Service layer."""
from __future__ import annotations

import datetime

from database import Database
from exceptions import NotFoundError, ValidationException
from models import Notification, Order


class NotificationService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def send_notification(self, order_id: int, message: str, sent_to: str) -> None:
        """Send a notification to a specified recipient."""
        order = self.db.order_repo.find_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        notification = Notification(id=None, message=message, order_id=order_id, sent_at=datetime.datetime.now(), sent_to=sent_to)
        self.db.notification_repo.create(notification)

    def send_confirmation_notification(self, order: Order) -> None:
        """Send a confirmation notification for the given order."""
        if not order:
            raise ValidationException('Order must be provided')
        message = f'Thank you for your order! Your order #{order.id} is confirmed and will be processed shortly.'
        self.send_notification(order.id, message, order.customer_id)

    def log_notification(self, order_id: int, message: str, sent_to: str) -> None:
        """Log a notification (for audit purposes) without sending it."""
        notification = Notification(id=None, message=message, order_id=order_id, sent_at=datetime.datetime.now(), sent_to=sent_to)
        self.db.notification_repo.create(notification)

