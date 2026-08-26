"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from exceptions import (
    BulkUpdateConflictError,
    TransactionFailedError,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def create_product(self, name: str, description: Optional[str] = None, price: float = None, stock_quantity: int = None, category: Optional[str] = None) -> bool:
        product = Product(name=name, description=description, price=price, stock_quantity=stock_quantity, category=category, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def get_product(self, product_id: int) -> Optional[Product]:
        return self.product_repo.get_by_id(product_id)

    def update_product(self, product_id: int, name: Optional[str] = None, description: Optional[str] = None, price: Optional[float] = None, stock_quantity: Optional[int] = None, category: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'name': name, 'description': description, 'price': price, 'stock_quantity': stock_quantity, 'category': category}.items() if v is not None}
        return self.product_repo.update(product_id, data)

    def delete_product(self, product_id: int) -> bool:
        return self.product_repo.delete(product_id)

    def get_products_by_category_and_price_range(self, category: Optional[str]=None, min_price: Optional[float]=None, max_price: Optional[float]=None) -> list[Product]:
        return self.product_repo.get_products_by_category_and_price_range(category, min_price, max_price)

    def bulk_update_stock(self, product_ids: list[int], new_stock_quantity: int) -> bool:
        try:
            return self.product_repo.bulk_update_stock(product_ids, new_stock_quantity)
        except BulkUpdateConflictError:
            raise
        except Exception as e:
            raise TransactionFailedError(f'Failed to update stock: {str(e)}')

