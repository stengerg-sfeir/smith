"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from database import Database
from models import Order, Product
from order_repository import OrderRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)

    def add_product(self, name: str, price: str) -> None:
        product = Product(name=name, price=price, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def list_order(self, customer_name: Optional[str] = None, created_at_from: Optional[str] = None, created_at_to: Optional[str] = None) -> list[Order]:
        return self.order_repo.list(customer_name=customer_name, created_at_from=created_at_from, created_at_to=created_at_to)

    def update_product(self, id: int, name: Optional[str] = None, price: Optional[str] = None) -> None:
        data = {k: v for k, v in {'name': name, 'price': price}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_order(self, id: int) -> None:
        return self.order_repo.delete(id)

    def get_product_report(self) -> dict:
        """
            Generates a product report that includes total revenue by product and the most popular product.
            Returns a dictionary with:
            - 'total_revenue_by_product': dict mapping product name to total revenue
            - 'most_popular_product': Product object with the highest total quantity sold
            """
        revenue_by_product = self.order_repo.get_total_revenue_by_product(start_date=datetime.date(2023, 1, 1), end_date=datetime.date(2023, 12, 31))
        most_popular_product = self.order_repo.get_most_popular_product()
        return {'total_revenue_by_product': revenue_by_product, 'most_popular_product': most_popular_product}

