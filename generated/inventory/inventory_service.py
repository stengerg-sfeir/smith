"""Service layer."""
from __future__ import annotations

from typing import Dict, List, Optional, Union

from category_repository import CategoryRepository
from database import Database
from exceptions import CategoryNotFoundError, ProductNotFoundError
from models import Product
from product_repository import ProductRepository


class InventoryService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.product_repo = ProductRepository(db)

    def add_product(self, sku: str, name: str, category_id: int, price_cents: int, stock_qty: int) -> None:
        if category_id is not None:
            if self.category_repo.get_by_id(category_id) is None:
                raise CategoryNotFoundError(category_id)
        product = Product(sku=sku, name=name, category_id=category_id, price_cents=price_cents, stock_qty=stock_qty)
        return self.product_repo.create(product)

    def update_product(self, id: int, data: Dict[str, Optional[Union[str, int, bool]]]) -> None:
        self.product_repo.update(id, data)

    def delete_product(self, id: int) -> None:
        self.product_repo.delete(id)

    def get_product_by_id(self, id: int) -> Optional[Product]:
        return self.product_repo.get_by_id(id)

    def list_products(self, category_id: Optional[int] = None, low_only: Optional[bool] = None) -> List[Product]:
        return self.product_repo.list(category_id=category_id)

    def restock(self, id: int, qty: int) -> None:
        if qty <= 0:
            raise ValueError("Restock quantity must be positive")

        product = self.product_repo.get_by_id(id)
        if product is None:
            raise ProductNotFoundError(id)

        new_stock = product.stock_qty + qty
        product.stock_qty = new_stock
        self.product_repo.update(id, {"stock_qty": new_stock})

    def low_stock_report(self) -> List[Product]:
        threshold = 10  # Define low stock threshold
        low_stock_products = []

        for product in self.product_repo.list():
            if product.stock_qty <= threshold:
                low_stock_products.append(product)

        return low_stock_products

    def stock_value_by_category(self) -> Dict[str, int]:
        category_value = {}

        for product in self.product_repo.list():
            category_name = self.category_repo.get_by_id(product.category_id).name if product.category_id else "Unknown"

            if category_name not in category_value:
                category_value[category_name] = 0

            category_value[category_name] += product.price_cents * product.stock_qty

        return category_value

