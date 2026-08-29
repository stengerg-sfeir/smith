"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from database import Database
from exceptions import (
    InvalidArgumentException,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def create_product(self, name: str, category: str, price: float, quantity: int) -> Optional[Product]:
        product = Product(name=name, category=category, price=price, quantity=quantity)
        return self.product_repo.create(product)

    def get_products_by_category(self, category: str) -> List[Product]:
        """Retrieve all products belonging to a specific category."""
        if not category:
            raise InvalidArgumentException('Category must be provided.')
        return self.product_repo.get_products_by_category_and_threshold(category, float('inf'))

    def get_products_below_threshold(self, threshold: int) -> List[Product]:
        """Retrieve products with quantity below a specified threshold."""
        if threshold < 0:
            raise InvalidArgumentException('Threshold must be a non-negative integer.')
        return self.product_repo.get_products_by_category_and_threshold('all', threshold)

    def update_product(self, product_id: int, name: Optional[str] = None, category: Optional[str] = None, price: Optional[float] = None, quantity: Optional[int] = None) -> Optional[Product]:
        data = {k: v for k, v in {'name': name, 'category': category, 'price': price, 'quantity': quantity}.items() if v is not None}
        return self.product_repo.update(product_id, data)

    def delete_product(self, product_id: int) -> bool:
        return self.product_repo.delete(product_id)

    def get_product_count_by_category(self, category: str) -> int:
        """Get the count of products in a specific category."""
        if not category:
            raise InvalidArgumentException('Category must be provided.')
        return self.product_repo.get_product_count_by_category(category)

    def get_low_stock_products(self) -> List[Product]:
        """Retrieve products with low stock (quantity less than 10)."""
        return self.product_repo.get_low_stock_products()

    def get_products_with_price_range(self, min_price: float, max_price: float) -> List[Product]:
        """Retrieve products within a specified price range."""
        if min_price < 0 or max_price < 0:
            raise InvalidArgumentException('Price range must be non-negative.')
        if min_price > max_price:
            raise InvalidArgumentException('Minimum price must be less than or equal to maximum price.')
        return self.product_repo.get_products_with_price_range(min_price, max_price)

    def list_product(self, category: str, threshold: int) -> List[Product]:
        return self.product_repo.list(category=category, threshold=threshold)

