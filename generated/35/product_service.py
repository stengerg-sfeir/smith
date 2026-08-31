"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from exceptions import (
    BulkUpdateConflictError,
    InvalidProductDataError,
    NotFoundError,
    TransactionFailedError,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def add_product(self, name: str, description: Optional[str] = None, price: str = None, stock_quantity: int = None, category: str = None) -> bool:
        product = Product(name=name, description=description, price=price, stock_quantity=stock_quantity, category=category, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def list_product(self, name: Optional[str] = None, category: Optional[str] = None, price_min: Optional[str] = None, price_max: Optional[str] = None, stock_min: Optional[str] = None, stock_max: Optional[str] = None) -> list[Product]:
        return self.product_repo.list(name=name, category=category, price_min=price_min, price_max=price_max, stock_min=stock_min, stock_max=stock_max)

    def update_product(self, id: int, name: Optional[str] = None, description: Optional[str] = None, price: Optional[str] = None, stock_quantity: Optional[int] = None, category: Optional[str] = None) -> bool:
        data = {k: v for k, v in {'name': name, 'description': description, 'price': price, 'stock_quantity': stock_quantity, 'category': category}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_product(self, id: int) -> bool:
        return self.product_repo.delete(id)

    def bulk_update_product(self, ids: str, name: Optional[str]=None, description: Optional[str]=None, price: Optional[str]=None, stock_quantity: int=None, category: Optional[str]=None) -> bool:
        if not ids:
            raise InvalidProductDataError('Product IDs are required for bulk update.')
        try:
            product_ids = [int(id.strip()) for id in ids.split(',')]
        except ValueError:
            raise InvalidProductDataError('Product IDs must be valid integers.')
        for product_id in product_ids:
            if not self.product_repo.get_by_id(product_id):
                raise NotFoundError(f'Product with ID {product_id} not found.')
        updates = []
        for product_id in product_ids:
            update_data = {}
            if name is not None:
                update_data['name'] = name
            if description is not None:
                update_data['description'] = description
            if price is not None:
                try:
                    price_float = float(price)
                    update_data['price'] = price_float
                except ValueError:
                    raise InvalidProductDataError('Price must be a valid number.')
            if stock_quantity is not None:
                update_data['stock_quantity'] = stock_quantity
            if category is not None:
                update_data['category'] = category
            if update_data:
                updates.append({'id': product_id, 'data': update_data})
        try:
            for update in updates:
                self.product_repo.update(update['id'], update['data'])
            return True
        except Exception as e:
            if isinstance(e, (BulkUpdateConflictError, TransactionFailedError)):
                raise
            else:
                raise TransactionFailedError('Bulk update failed due to an unexpected error.')

