"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from database import Database
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def search_products(self, name: Optional[str]=None, category: Optional[str]=None, max_price: Optional[float]=None, min_quantity: Optional[int]=None) -> List[Product]:
        products = []
        if name:
            products = self.product_repo.search_products_by_name(name)
        elif category:
            products = self.product_repo.filter_products_by_category(category)
        elif max_price is not None:
            products = self.product_repo.filter_products_by_max_price(max_price)
        elif min_quantity is not None:
            products = self.product_repo.filter_products_by_min_quantity(min_quantity)
        else:
            products = self.product_repo.get_all()
        if name and category:
            products = [p for p in products if p.category == category]
        elif name and max_price:
            products = [p for p in products if p.price <= max_price]
        elif name and min_quantity:
            products = [p for p in products if p.quantity >= min_quantity]
        elif category and max_price:
            products = [p for p in products if p.category == category and p.price <= max_price]
        elif category and min_quantity:
            products = [p for p in products if p.category == category and p.quantity >= min_quantity]
        elif max_price and min_quantity:
            products = [p for p in products if p.price <= max_price and p.quantity >= min_quantity]
        return products

    def get_product_count(self) -> int:
        return self.product_repo.get_product_count()

    def get_product_summary(self) -> Dict[str, Any]:
        results = {}
        for row in self.product_repo.list():
            key = row.category
            results[key] = results.get(key, 0) + row.price
        return results

    def export_products_to_csv(self, file_path: str) -> None:
        rows = self.product_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'name', 'category', 'price',
                'quantity',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.name, row.category, row.price,
                    row.quantity,
                ])

    def find_duplicate_products(self) -> List[Product]:
        products = self.product_repo.get_all()
        seen = set()
        duplicates = []
        for product in products:
            product_key = (product.name, product.category)
            if product_key in seen:
                duplicates.append(product)
            else:
                seen.add(product_key)
        return duplicates

    def get_products_below_category_threshold(self, category: str) -> List[Product]:
        category_products = self.product_repo.filter_products_by_category(category)
        if not category_products:
            return []
        avg_quantity = sum((p.quantity for p in category_products)) / len(category_products)
        return [p for p in category_products if p.quantity < avg_quantity]

