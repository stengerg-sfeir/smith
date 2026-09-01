"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from database import Database
from exceptions import (
    FilterException,
    NotFoundError,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def add_product(self, name: str, category: str, price: str, quantity: int) -> None:
        product = Product(name=name, category=category, price=price, quantity=quantity)
        return self.product_repo.create(product)

    def list_product(self, category: Optional[str] = None, threshold: Optional[str] = None) -> List[Product]:
        return self.product_repo.list(category=category, threshold=threshold)

    def update_product(self, id: int, name: Optional[str] = None, category: Optional[str] = None, price: Optional[str] = None, quantity: Optional[int] = None) -> None:
        data = {k: v for k, v in {'name': name, 'category': category, 'price': price, 'quantity': quantity}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_product(self, id: int) -> None:
        return self.product_repo.delete(id)

    def filter_product(self, id: int) -> List[Product]:
        """Filter products by ID."""
        try:
            product = self.product_repo.get_by_id(id)
            if not product:
                raise NotFoundError(f'Product with id {id} not found')
            return [product]
        except Exception as e:
            if isinstance(e, NotFoundError):
                raise e
            raise FilterException(f'Error filtering product: {str(e)}')

