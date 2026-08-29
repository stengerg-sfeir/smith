"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Any, Dict, List

from database import Database
from exceptions import NotFoundError
from models import Notification, Order
from order_repository import OrderRepository


class NotificationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)

    def confirm_order(self, order_id: int) -> None:
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        order.status = 'confirmed'
        self.order_repo.update(order.id, {'status': 'confirmed'})

    def get_orders_by_customer_and_date_range(self, customer_id: int, start_date: datetime, end_date: datetime) -> List[Order]:
        return self.order_repo.get_order_by_customer_and_date_range(customer_id, start_date, end_date)

    def get_orders_with_status_and_total(self, status: str, min_total: float) -> List[Order]:
        return self.order_repo.get_orders_with_status_and_total(status, min_total)

    def send_confirmation_notification(self, order: Order) -> None:
        if not order:
            raise NotFoundError('Order not found')
        notification = Notification(message=f'Thank you for your order! Order #{order.id} is confirmed.', order_id=order.id, sent_to=order.customer_id, sent_at=datetime.datetime.now())
        self.order_repo.create(notification)

    def export_orders_to_csv(self, file_path: str, filter_params: Dict[str, Any]) -> None:
        rows = self.order_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'customer_id', 'status', 'created_at',
                'updated_at', 'total_amount',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.customer_id, row.status, row.created_at,
                    row.updated_at, row.total_amount,
                ])

    def get_order_count_by_status(self) -> Dict[str, int]:
        return self.order_repo.get_order_count_by_status()

