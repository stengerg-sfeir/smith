"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from database import Database
from exceptions import (
    NotFoundError,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def add_product(self, sku: str, name: str, category: str, price: str, stock_quantity: int) -> None:
        product = Product(sku=sku, name=name, category=category, price=price, stock_quantity=stock_quantity)
        return self.product_repo.create(product)

    def list_product(self, sku: Optional[str] = None, name: Optional[str] = None, category: Optional[str] = None, min_price: Optional[str] = None, max_price: Optional[str] = None, min_stock: Optional[str] = None, max_stock: Optional[str] = None) -> List[Product]:
        return self.product_repo.list(sku=sku, name=name, category=category, min_price=min_price, max_price=max_price, min_stock=min_stock, max_stock=max_stock)

    def update_product(self, id: int, sku: Optional[str] = None, name: Optional[str] = None, category: Optional[str] = None, price: Optional[str] = None, stock_quantity: Optional[int] = None) -> None:
        data = {k: v for k, v in {'sku': sku, 'name': name, 'category': category, 'price': price, 'stock_quantity': stock_quantity}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_product(self, id: int) -> None:
        return self.product_repo.delete(id)

    def search_product(self, term: str) -> List[Product]:
        """
            Search for products by name or category using the provided term.
            Uses the search_products method of the repository with the term and category.
            """
        return self.product_repo.search_products(term, None)

    def filter_product(self, id: int) -> List[Product]:
        """
            Filter products by ID.
            Uses the get_by_id method of the repository to retrieve a single product by ID.
            """
        product = self.product_repo.get_by_id(id)
        if product is None:
            raise NotFoundError(f'Product with ID {id} not found')
        return [product]

