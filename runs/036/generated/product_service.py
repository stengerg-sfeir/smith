"""Service layer."""
from __future__ import annotations

from typing import Dict, List

from category_repository import CategoryRepository
from database import Database
from exceptions import (
    CategoryNotFoundError,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.product_repo = ProductRepository(db)

    def get_products_by_category_name(self, category_name: str) -> List[Product]:
        category = self.category_repo.get_category_by_name(category_name)
        if not category:
            raise CategoryNotFoundError(f"Category '{category_name}' not found")
        products = self.product_repo.get_products_by_category_name(category_name)
        return products

    def get_product_count_by_category(self) -> Dict[str, int]:
        results = {}
        for row in self.product_repo.list():
            key = row.category_id
            results[key] = results.get(key, 0) + row.price
        return results

    def get_products_in_price_range(self, min_price: float, max_price: float) -> List[Product]:
        return self.product_repo.get_products_in_price_range(min_price, max_price)

    def get_products_with_category_details(self) -> List[Dict]:
        raise NotImplementedError()

    def search_products_by_name(self, query: str) -> List[Product]:
        """Search products by name using the product repository."""
        return self.product_repo.search_products_by_name(query)

    def get_category_product_summary(self) -> Dict:
        results = {}
        for row in self.product_repo.list():
            key = row.category_id
            results[key] = results.get(key, 0) + row.price
        return results

    def get_products_with_category_details(self) -> List[Dict]:
        raise NotImplementedError()

