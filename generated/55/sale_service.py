"""Service layer."""
from __future__ import annotations

import datetime

from database import Database
from exceptions import (
    InvalidProductError,
    OutOfStockError,
    StockUnderflowError,
    ValidationError,
)
from models import Product, Sale
from product_repository import ProductRepository


class SaleService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def add_product(self, name: str, description: str, price: str, stock_quantity: int) -> bool:
        product = Product(name=name, description=description, price=price, stock_quantity=stock_quantity, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def sell_product(self, id: int) -> bool:
        product = self.product_repo.get_product_by_id(id)
        if not product:
            raise InvalidProductError(f'Product with id {id} not found')
        if product.stock_quantity <= 0:
            raise OutOfStockError(f'Product with id {id} is out of stock')
        sale = Sale(id=None, product_id=product.id, quantity=1, sale_price=product.price, sold_at=datetime.datetime.now())
        new_stock = product.stock_quantity - 1
        if new_stock < 0:
            raise StockUnderflowError(f'Stock underflow for product with id {id}')
        updated_product = Product(created_at=product.created_at, description=product.description, id=product.id, name=product.name, price=product.price, stock_quantity=new_stock, updated_at=datetime.datetime.now())
        try:
            self.product_repo.update(product.id, {'stock_quantity': new_stock})
            return True
        except Exception as e:
            raise ValidationError(f'Failed to update product stock: {str(e)}')

    def check_product(self, id: int) -> dict[str, any]:
        results = {}
        for row in self.product_repo.list():
            key = row.id
            results[key] = results.get(key, 0) + row.stock_quantity
        return results

