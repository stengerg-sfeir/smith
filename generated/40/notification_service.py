"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List

from database import Database
from exceptions import NotFoundError, NotificationFailedException
from models import Order
from notification_repository import NotificationRepository
from order_repository import OrderRepository


class NotificationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.notification_repo = NotificationRepository(db)
        self.order_repo = OrderRepository(db)

    def confirm_notification(self, id: int) -> None:
        notification = self.notification_repo.get_by_id(id)
        if not notification:
            raise NotFoundError(f'Notification with id {id} not found')
        order_id = notification.order_id
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        if order.status not in ['pending', 'processing']:
            raise NotificationFailedException(f'Cannot confirm notification for order {order_id}. Order status is {order.status}')
        order.status = 'confirmed'
        order.updated_at = datetime.datetime.now()
        self.order_repo.update(order.id, {'status': 'confirmed', 'updated_at': order.updated_at.isoformat()})
        notification.sent_at = datetime.datetime.now()
        notification.sent_to = order.customer_id
        self.notification_repo.update(notification.id, {'sent_at': notification.sent_at.isoformat(), 'sent_to': notification.sent_to})

    def list_notification(self, order_id: str, sent_at: str, sent_at_end: str) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.notification_repo.list(order_id=order_id, sent_at=sent_at, sent_at_end=sent_at_end):
            key = (row.sent_to)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'sent_to': key[0],
                    'count': len(group),
                })
        return results

    def add_order(self, customer_id: int, status: str, total_amount: str) -> None:
        order = Order(customer_id=customer_id, status=status, total_amount=total_amount, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.order_repo.create(order)

