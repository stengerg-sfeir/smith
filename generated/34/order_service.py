"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from models import Order
from order_line_repository import OrderLineRepository
from order_repository import OrderRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.order_line_repo = OrderLineRepository(db)

    def add_order(self, status: str) -> Optional[dict]:
        order = Order(status=status, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.order_repo.create(order)

