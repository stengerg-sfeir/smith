"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import List, Optional

from database import Database
from exceptions import (
    ProductNotFoundError,
)
from models import OrderItem
from order_repository import OrderRepository
from product_repository import ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)

    def create_order_item(self, order_id: int, product_id: int, quantity: int, unit_price: float) -> bool:
        if product_id is not None:
            if self.product_repo.get_by_id(product_id) is None:
                raise ProductNotFoundError(product_id)
        order_item = OrderItem(order_id=order_id, product_id=product_id, quantity=quantity, unit_price=unit_price, created_at=datetime.datetime.now().isoformat())
        # Assuming OrderItem creation requires a repository, but no orderitem_repository found
        # This is a placeholder - actual implementation depends on repository structure
        return True  # Placeholder return; actual logic would use a proper repository

    def get_order_item_by_id(self, order_item_id: int) -> Optional[OrderItem]:
        # Placeholder - no orderitem_repository available
        return None

    def update_order_item(self, order_item_id: int, quantity: int, unit_price: float) -> bool:
        data = {k: v for k, v in {'quantity': quantity, 'unit_price': unit_price}.items() if v is not None}
        # Placeholder - no orderitem_repository available
        return False

    def delete_order_item(self, order_item_id: int) -> bool:
        # Placeholder - no orderitem_repository available
        return False

    def get_order_items_by_order_id(self, order_id: int) -> List[OrderItem]:
        # Placeholder - no orderitem_repository available
        return []

    def get_order_items_by_product(self, product_name: str, min_quantity: int) -> List[OrderItem]:
        # Placeholder - no orderitem_repository available
        return []

    def get_order_items_with_high_value(self, min_total_value: float) -> List[OrderItem]:
        # Placeholder - no orderitem_repository available
        return []

    def export_order_items_to_csv(self, file_path: str, start_date: datetime, end_date: datetime) -> None:
        # Placeholder - no orderitem_repository available
        rows = []
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'order_id', 'product_id', 'quantity',
                'unit_price', 'created_at',
            ])
