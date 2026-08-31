"""Service layer."""
from __future__ import annotations

import csv
import datetime

from database import Database
from exceptions import (
    NotFoundError,
)
from models import Order, Product
from order_repository import OrderRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)

    def create_order(self, customer_name: str, items: list[dict[str, any]]) -> int:
        order = Order(customer_name=customer_name, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.order_repo.create(order)

    def get_order_total_amount(self, order_id: int) -> float:
        rows = self.order_item_repo.list(order_id=order_id)
        return sum(e.unit_price for e in rows)

    def list_orders_by_customer(self, customer_name: str, start_date: datetime, end_date: datetime) -> list[Order]:
        """
            Retrieves orders for a specific customer within a date range.
            """
        return self.order_repo.list_orders_by_customer(customer_name, start_date, end_date)

    def get_order_with_items(self, order_id: int) -> OrderWithItems:
        """
            Retrieves an order with its associated items.
            """
        order = self.order_repo.get_order_with_items(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        return order

    def get_total_revenue_by_product(self, start_date: datetime, end_date: datetime) -> dict[str, float]:
        results = {}
        for row in self.order_item_repo.list(start_date=start_date, end_date=end_date):
            key = row.product_id
            results[key] = results.get(key, 0) + row.unit_price
        return results

    def get_most_popular_product(self) -> Product:
        """
            Retrieves the product with the highest total quantity sold.
            """
        return self.order_repo.get_most_popular_product()

    def get_orders_with_quantity_over_limit(self, min_quantity: int) -> list[Order]:
        """
            Retrieves orders where at least one item has a quantity exceeding the specified limit.
            """
        return self.order_repo.get_orders_with_quantity_over_limit(min_quantity)

    def export_orders_to_csv(self, file_path: str, customer_name: str, start_date: datetime, end_date: datetime) -> None:
        rows = self.order_repo.list(customer_name=customer_name, )
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'customer_name', 'created_at', 'updated_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.customer_name, row.created_at, row.updated_at,
                ])

