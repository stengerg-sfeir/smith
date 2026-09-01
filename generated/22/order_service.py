"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, Optional

from database import Database
from models import Order, Product
from order_repository import OrderRepository
from product_repository import ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)

    def add_product(self, name: str, price: str) -> None:
        product = Product(name=name, price=price, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def list_order(self, customer_name: Optional[str] = None, created_at_from: Optional[str] = None, created_at_to: Optional[str] = None) -> list[Order]:
        return self.order_repo.list(customer_name=customer_name, created_at_from=created_at_from, created_at_to=created_at_to)

    def update_product(self, id: int, name: Optional[str] = None, price: Optional[str] = None) -> None:
        data = {k: v for k, v in {'name': name, 'price': price}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_order(self, id: int) -> None:
        return self.order_repo.delete(id)

    def get_product_report(self, id: int) -> Dict[str, Any]:
        results = {}
        for row in self.order_item_repo.list():
            key = row.product_id
            results[key] = results.get(key, 0) + row.unit_price
        return results

