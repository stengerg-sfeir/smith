"""Service layer."""
from __future__ import annotations

from typing import List, Optional

from database import Database
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def create_product(self, name: str, description: Optional[str] = None, price: float = None, quantity: int = None) -> Product:
        product = Product(name=name, description=description, price=price, quantity=quantity)
        return self.product_repo.create(product)

    def get_product_by_name(self, name: str) -> Optional[Product]:
        return self.product_repo.get_product_by_name(name)

    def get_products_by_price_range(self, min_price: float, max_price: float) -> List[Product]:
        return self.product_repo.get_products_by_price_range(min_price, max_price)

    def get_products_with_low_stock(self) -> List[Product]:
        return self.product_repo.get_products_with_low_stock()

    def get_product_count(self) -> int:
        return self.product_repo.get_product_count()

    def get_total_value_of_inventory(self) -> float:
        results = {}
        for row in self.product_repo.list():
            key = row.name
            results[key] = results.get(key, 0) + row.price
        return results

    def search_products(self, query: str) -> List[Product]:
        return self.product_repo.search_products(query)

    def get_products_by_category(self, category: str) -> List[Product]:
        return self.product_repo.get_products_by_category(category)

    def get_product_with_highest_price(self) -> Optional[Product]:
        return self.product_repo.get_product_with_highest_price()

    def get_product_with_lowest_price(self) -> Optional[Product]:
        return self.product_repo.get_product_with_lowest_price()

