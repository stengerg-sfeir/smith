"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from category_repository import CategoryRepository
from database import Database
from exceptions import CategoryNotFoundError
from models import Category, Product
from product_repository import ProductRepository


class CategoryService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.product_repo = ProductRepository(db)

    def add(self, sku: str, name: str, category_id: int, price_cents: int, stock_qty: int) -> None:
        return None

    def update(self, id: int, name: Optional[str] = None, price_cents: Optional[int] = None, category_id: Optional[int] = None) -> None:
        return None

    def delete(self, id: int) -> None:
        return None

    def list(self, category_id: Optional[int] = None) -> List[Product]:
        return []

    def report(self) -> List[Product]:
        categories = self.category_repo.get_all()
        low_stock_products = []
        for category in categories:
            category_id = category.id
            low_stock_products_in_category = self.product_repo.find_low_stock_products(category_id)
            low_stock_products.extend(low_stock_products_in_category)
        return low_stock_products

    def add(self, name: str, description: Optional[str] = None, reorder_threshold: Optional[int] = None) -> None:
        return None

    def list(self) -> List[Category]:
        return []

    def update(self, id: int, name: Optional[str] = None, description: Optional[str] = None, reorder_threshold: Optional[int] = None) -> None:
        return None

    def delete(self, id: int) -> None:
        return None

    def add_product(self, sku: str, name: str, category_id: int, price_cents: int, stock_qty: int) -> int:
        if category_id is not None:
            if self.category_repo.get_by_id(category_id) is None:
                raise CategoryNotFoundError(category_id)
        product = Product(sku=sku, name=name, category_id=category_id, price_cents=price_cents, stock_qty=stock_qty)
        return self.product_repo.create(product)

    def list_product(self, category_id: int, low_only: bool) -> List[Product]:
        return self.product_repo.list(category_id=category_id, low_only=low_only)

    def update_product(self, id: int, name: str, price_cents: int, category_id: int) -> bool:
        data = {k: v for k, v in {'name': name, 'price_cents': price_cents, 'category_id': category_id}.items() if v is not None}
        return self.product_repo.update(id, data)

