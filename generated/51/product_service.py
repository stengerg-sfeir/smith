"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def add_product(self, sku: str, name: str, category: str, price: str) -> bool:
        product = Product(sku=sku, name=name, category=category, price=price, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def check_product(self, id: int) -> Optional[Product]:
        """Retrieve a product by its ID."""
        return self.product_repo.get_by_id(id)

    def update_product(self, id: int, sku: Optional[str] = None, name: Optional[str] = None, category: Optional[str] = None, price: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'sku': sku, 'name': name, 'category': category, 'price': price}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_product(self, id: int) -> bool:
        return self.product_repo.delete(id)

    def list_product(self, sku: Optional[str] = None, category: Optional[str] = None, price: Optional[str] = None) -> list[Product]:
        return self.product_repo.list(sku=sku, category=category, price=price)

