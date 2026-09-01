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

    def add_product(self, name: str, price: str, quantity: int) -> bool:
        product = Product(name=name, price=price, quantity=quantity, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def list_product(self, name: Optional[str] = None, price: Optional[str] = None, price_gte: Optional[str] = None, price_lte: Optional[str] = None, quantity: Optional[str] = None, quantity_gte: Optional[str] = None, quantity_lte: Optional[str] = None) -> list[Product]:
        return self.product_repo.list(name=name, price=price, price_gte=price_gte, price_lte=price_lte, quantity=quantity, quantity_gte=quantity_gte, quantity_lte=quantity_lte)

    def update_product(self, id: int, name: Optional[str] = None, price: Optional[str] = None, quantity: Optional[int] = None) -> bool:
        data = {k: v for k, v in {'name': name, 'price': price, 'quantity': quantity}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_product(self, id: int) -> bool:
        return self.product_repo.delete(id)

