"""Service layer."""
from __future__ import annotations

import csv
from typing import Dict, List, Optional

from database import Database
from exceptions import (
    NotFoundError,
    OutOfStockError,
    ValidationError,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def create_product(self, sku: str, name: str, category: str, price: float, stock_quantity: int) -> Optional[Product]:
        product = Product(sku=sku, name=name, category=category, price=price, stock_quantity=stock_quantity)
        return self.product_repo.create(product)

    def get_product_by_sku(self, sku: str) -> Optional[Product]:
        """Retrieve a product by its SKU."""
        products = self.product_repo.list(sku=sku)
        return products[0] if products else None

    def get_products_by_category(self, category: str) -> List[Product]:
        """Retrieve all products belonging to a specific category."""
        return self.product_repo.get_products_by_category(category)

    def search_products(self, query: str, category: Optional[str]=None) -> List[Product]:
        """Search products by query string, optionally filtered by category."""
        return self.product_repo.search_products(query, category)

    def get_low_stock_products(self) -> List[Product]:
        """Retrieve products with low stock (stock quantity below threshold)."""
        return self.product_repo.get_products_low_stock()

    def update_product_stock(self, sku: str, new_stock: int) -> bool:
        """Update the stock quantity for a product by SKU."""
        try:
            product = self.product_repo.get_by_id(self.product_repo.get_product_by_sku(sku).id)
            if not product:
                raise NotFoundError(f'Product with SKU {sku} not found')
            if new_stock < 0:
                raise ValidationError('Stock quantity cannot be negative')
            self.product_repo.update(product.id, {'stock_quantity': new_stock})
            return True
        except Exception as e:
            if isinstance(e, (NotFoundError, ValidationError, OutOfStockError)):
                raise e
            raise RuntimeError(f'Failed to update product stock: {str(e)}')

    def delete_product(self, sku: str) -> bool:
        return self.product_repo.delete(sku)

    def get_product_count_by_category(self) -> Dict[str, int]:
        results = {}
        for row in self.product_repo.list():
            key = row.category
            results[key] = results.get(key, 0) + row.stock_quantity
        return results

    def export_products_to_csv(self, file_path: str) -> None:
        rows = self.product_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'sku', 'name', 'category',
                'price', 'stock_quantity',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.sku, row.name, row.category,
                    row.price, row.stock_quantity,
                ])

    def get_products_with_price_range(self, min_price: float, max_price: float) -> List[Product]:
        """Retrieve products within a specified price range."""
        return self.product_repo.get_products_with_price_range(min_price, max_price)

