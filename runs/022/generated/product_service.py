"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Dict, List, Optional

from database import Database
from exceptions import (
    InvalidPriceError,
    ProductNotFoundError,
    ValidationError,
)
from models import Product
from order_repository import OrderRepository
from product_repository import ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)

    def create_product(self, name: str, price: float) -> int:
        product = Product(name=name, price=price, created_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def get_product_by_name(self, product_name: str) -> Optional[Product]:
        return self.product_repo.get_product_by_name(product_name)

    def get_products_by_price_range(self, min_price: float, max_price: float) -> List[Product]:
        return self.product_repo.get_products_by_price_range(min_price, max_price)

    def get_product_usage_count(self, product_name: str) -> int:
        return self.product_repo.get_product_usage_count(product_name)

    def get_top_products_by_total_quantity_sold(self) -> List[Product]:
        return self.product_repo.get_top_products_by_total_quantity_sold()

    def get_products_with_low_stock_alert(self, threshold: int) -> List[Product]:
        return self.product_repo.get_products_with_low_stock_alert(threshold)

    def get_product_sales_summary_by_date_range(self, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        return self.product_repo.get_product_sales_summary_by_date_range(start_date, end_date)

    def get_product_with_highest_average_order_price(self) -> Optional[Product]:
        return self.product_repo.get_product_with_highest_average_order_price()

    def update_product_price(self, product_name: str, new_price: float) -> bool:
        product = self.product_repo.get_product_by_name(product_name)
        if not product:
            raise ProductNotFoundError(f"Product with name '{product_name}' not found")
        if new_price < 0:
            raise InvalidPriceError('Price cannot be negative')
        try:
            self.product_repo.update(product.id, {'price': new_price})
            return True
        except Exception as e:
            raise ValidationError(f'Failed to update product price: {str(e)}')

    def export_product_sales_summary_to_csv(self, file_path: str, start_date: datetime, end_date: datetime) -> None:
        sales_summary = self.get_product_sales_summary_by_date_range(start_date, end_date)
        with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(['Product Name', 'Total Sales'])
            for product_name, total_sales in sales_summary.items():
                writer.writerow([product_name, total_sales])
