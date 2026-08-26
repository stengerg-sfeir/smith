"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Dict, List, Optional

from database import Database
from models import Product
from order_repository import OrderRepository
from product_repository import ProductRepository
from user_repository import UserRepository


class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)
        self.user_repo = UserRepository(db)

    def create_product(self, name: str, description: Optional[str] = None, price: float = None, stock_quantity: int = None) -> Optional[Product]:
        product = Product(name=name, description=description, price=price, stock_quantity=stock_quantity, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def get_product_by_id(self, product_id: int) -> Optional[Product]:
        return self.product_repo.get_by_id(product_id)

    def get_products_by_category_and_price_range(self, category: str, min_price: float, max_price: float) -> List[Product]:
        """Retrieve products by category and price range."""
        return self.product_repo.get_products_by_category(category, min_price, max_price)

    def get_top_selling_products(self, limit: int) -> List[Product]:
        """Retrieve the top selling products based on sales volume."""
        return self.product_repo.get_top_selling_products(limit)

    def get_products_with_low_stock(self) -> List[Product]:
        """Retrieve products with low stock levels."""
        return self.product_repo.get_products_with_low_stock()

    def export_products_to_csv(self, file_path: str) -> None:
        rows = self.product_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'name', 'description', 'price',
                'stock_quantity', 'created_at', 'updated_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.name, row.description, row.price,
                    row.stock_quantity, row.created_at, row.updated_at,
                ])

    def get_product_sales_trend(self, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Retrieve sales trend data for products over a date range."""
        return self.product_repo.get_product_sales_trend(start_date, end_date)

