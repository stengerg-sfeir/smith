"""Service layer."""
from __future__ import annotations

import datetime

from database import Database
from exceptions import NotFoundError, NotificationFailedException, ValidationException
from models import Notification, Order
from notification_repository import NotificationRepository
from order_repository import OrderRepository


class NotificationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.notification_repo = NotificationRepository(db)
        self.order_repo = OrderRepository(db)

    def send_notification(self, order_id: int, message: str, sent_to: str) -> None:
        """Send a notification to a recipient for a given order."""
        try:
            order = self.order_repo.get_by_id(order_id)
            if not order:
                raise NotFoundError(f'Order with id {order_id} not found')
            notification = Notification(message=message, order_id=order_id, sent_at=datetime.datetime.now(), sent_to=sent_to)
            self.notification_repo.create(notification)
        except Exception as e:
            raise NotificationFailedException(f'Failed to send notification: {str(e)}')

    def send_confirmation_notification(self, order: Order) -> None:
        """Send a confirmation notification for a given order."""
        if not order:
            raise ValidationException('Order must be provided')
        message = f'Thank you for your order! Order #{order.id} has been confirmed. Total amount: ${order.total_amount:.2f}. Status: {order.status}'
        self.send_notification(order.id, message, order.customer_id)

    def log_notification(self, order_id: int, message: str, sent_to: str) -> None:
        """Log a notification (for audit or debugging purposes)."""
        try:
            notification = Notification(message=message, order_id=order_id, sent_at=datetime.datetime.now(), sent_to=sent_to)
            self.notification_repo.create(notification)
        except Exception as e:
            raise NotificationFailedException(f'Failed to log notification: {str(e)}')
