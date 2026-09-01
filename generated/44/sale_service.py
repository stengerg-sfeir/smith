"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    OutOfStockError,
    ProductNotFoundError,
)
from models import Product, Sale
from product_repository import ProductRepository
from sale_repository import SaleRepository


class SaleService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.product_repo = ProductRepository(db)
        self.sale_repo = SaleRepository(db)

    def add_product(self, name: str, price: str, stock_quantity: int) -> None:
        product = Product(name=name, price=price, stock_quantity=stock_quantity, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def list_product(self) -> List[Product]:
        return self.product_repo.list()

    def record_product(self, id: int) -> None:
        """Records a product sale by checking product availability and creating a sale."""
        product = self.product_repo.get_by_id(id)
        if not product:
            raise ProductNotFoundError(f'Product with id {id} not found')
        if product.stock_quantity <= 0:
            raise OutOfStockError(f'Product with id {id} is out of stock')
        sale = Sale(customer_id=None, product_id=id, quantity=1, sale_date=datetime.datetime.now().strftime('%Y-%m-%d'), total_price=product.price)
        product.stock_quantity -= 1
        self.product_repo.update(id, {'stock_quantity': product.stock_quantity})
        self.sale_repo.create(sale)

    def check_product(self, id: int) -> Optional[Product]:
        """Checks if a product exists and is in stock."""
        product = self.product_repo.get_by_id(id)
        if not product:
            return None
        if product.stock_quantity <= 0:
            return None
        return product

