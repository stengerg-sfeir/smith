"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from database import Database
from models import Category, Product
from category_repository import CategoryRepository
from product_repository import ProductRepository
from exceptions import CategoryNotFoundError, ProductNotFoundError


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.product_repo = ProductRepository(db)

    def add_product(self, sku: str, name: str, category_id: int, price_cents: int, stock_qty: int) -> Product:
        if category_id is not None:
            if self.category_repo.get_by_id(category_id) is None:
                raise CategoryNotFoundError(category_id)
        product = Product(sku=sku, name=name, category_id=category_id, price_cents=price_cents, stock_qty=stock_qty)
        return self.product_repo.create(product)

    def update_product(self, id: int, data: dict[str, any]) -> Product:
        self.product_repo.update(id, data)

    def delete_product(self, id: int) -> None:
        return self.product_repo.delete(id)

    def get_product_by_id(self, id: int) -> Optional[Product]:
        return self.product_repo.get_by_id(id)

    def list_products(self, category_id: Optional[int] = None, low_only: Optional[bool] = None) -> list[Product]:
        return self.product_repo.list(category_id=category_id, low_only=low_only)

    def restock(self, id: int, qty: int) -> None:
        product = self.product_repo.get_by_id(id)
        if not product:
            raise ProductNotFoundError(f'Product with id {id} not found')
        new_stock = product.stock_qty + qty
        updated_product_data = {'stock_qty': new_stock}
        self.product_repo.update(id, updated_product_data)

    def low_stock_report(self) -> list[Product]:
        low_stock_products = self.product_repo.list_low_stock()
        return low_stock_products

    def stock_value_by_category(self) -> dict[str, int]:
        results = {}
        for row in self.product_repo.list():
            key = row.category_id
            results[key] = results.get(key, 0) + row.price_cents
        return results

    def add_category(self, name: str, description: str, reorder_threshold: int) -> int:
        category = Category(name=name, description=description, reorder_threshold=reorder_threshold)
        return self.category_repo.create(category)

    def update_category(self, id: int, name: str, description: str, reorder_threshold: int) -> bool:
        data = {k: v for k, v in {'name': name, 'description': description, 'reorder_threshold': reorder_threshold}.items() if v is not None}
        return self.category_repo.update(id, data)

    def delete_category(self, id: int) -> bool:
        return self.category_repo.delete(id)

