"""Service layer."""
from __future__ import annotations

from typing import Any, Dict, Optional

from database import Database
from exceptions import InsufficientStockError
from models import OrderItem
from order_repository import OrderRepository
from product_repository import ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)

    def place_product(self, id: int) -> Optional[Dict[str, Any]]:
        product = self.product_repo.get_by_id(id)
        if not product:
            return None
        if product.stock_quantity <= 0:
            raise InsufficientStockError(f"Product '{product.name}' has no stock available.")
        order_item = OrderItem(id=None, order_id=None, product_id=product.id, quantity=1)
        return {'product_id': product.id, 'name': product.name, 'price': product.price, 'stock_quantity': product.stock_quantity, 'order_item': {'product_id': product.id, 'quantity': 1}}

