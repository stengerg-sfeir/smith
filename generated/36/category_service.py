"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from category_repository import CategoryRepository
from database import Database
from models import Category
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.product_repo = ProductRepository(db)

    def get_category_by_name(self, category_name: str) -> Optional[Category]:
        return self.category_repo.get_category_by_name(category_name)

    def get_categories_with_product_count(self) -> List[Dict[str, Any]]:
        results = {}
        for row in self.product_repo.list():
            key = row.category_id
            results[key] = results.get(key, 0) + row.category_id
        return results

    def get_active_categories(self) -> List[Category]:
        return self.category_repo.get_active_categories()

    def get_category_product_count(self, category_name: str) -> int:
        return self.category_repo.get_category_product_count(category_name)

    def get_categories_by_product_price_range(self, min_price: float, max_price: float) -> List[Dict[str, Any]]:
        return self.category_repo.get_categories_by_product_price_range(min_price, max_price)

    def get_category_summary_by_price_band(self) -> Dict[str, int]:
        return self.category_repo.get_category_summary_by_price_band()

    def export_categories_to_csv(self, file_path: str) -> None:
        rows = self.category_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'name', 'created_at', 'updated_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.name, row.created_at, row.updated_at,
                ])

    def validate_category_deletion(self, category_name: str) -> bool:
        product_count = self.product_repo.get_product_count_by_category()
        category_product_count = product_count.get(category_name, 0)
        return category_product_count == 0

