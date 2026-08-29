"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from database import Database
from exceptions import (
    NotFoundError,
    ProductNotFoundError,
)
from models import Order, OrderItem, Product
from order_repository import OrderRepository
from product_repository import ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)

    def create_order(self, customer_name: str, order_items: List[Dict[str, int]]) -> int:
        order = Order(customer_name=customer_name, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.order_repo.create(order)

    def get_order_by_id(self, order_id: int) -> Optional[Order]:
        return self.order_repo.get_by_id(order_id)

    def update_order(self, order_id: int, customer_name: str, order_items: List[Dict[str, int]]) -> bool:
        data = {k: v for k, v in {'customer_name': customer_name}.items() if v is not None}
        return self.order_repo.update(order_id, data)

    def delete_order(self, order_id: int) -> bool:
        return self.order_repo.delete(order_id)

    def get_total_order_amount(self, order_id: int) -> float:
        """Calculate the total amount for a given order by summing up order items."""
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        order_items = self.order_repo.get_order_items_by_order_id(order_id)
        total_amount = sum((item.quantity * item.unit_price for item in order_items))
        return total_amount

    def get_orders_by_customer(self, customer_name: str) -> List[Order]:
        """Retrieve all orders for a given customer."""
        return self.order_repo.get_order_with_items_by_customer(customer_name)

    def get_order_items_by_product(self, product_name: str, min_quantity: int) -> List[OrderItem]:
        """Retrieve order items for a given product with minimum quantity."""
        product = self.product_repo.get_product_by_name(product_name)
        if not product:
            raise ProductNotFoundError(f"Product '{product_name}' not found")
        return self.order_repo.get_order_items_by_product_and_date_range(product_name=product_name, start_date=None, end_date=None)

    def get_orders_with_high_value_items(self, min_total_amount: float) -> List[Order]:
        """Retrieve orders that contain items with total value above a threshold."""
        return self.order_repo.get_orders_with_high_value_items(min_total_amount)

    def get_most_popular_product(self) -> Optional[Product]:
        """Retrieve the most popular product based on total quantity sold."""
        # Aggregate order items by product
        product_quantity_map = {}
        order_items = self.order_repo.get_all_order_items()
        for item in order_items:
            product_name = item.product_name
            quantity = item.quantity
            product_quantity_map[product_name] = product_quantity_map.get(product_name, 0) + quantity

        if not product_quantity_map:
            return None

        most_popular_product_name = max(product_quantity_map, key=product_quantity_map.get)
        product = self.product_repo.get_product_by_name(most_popular_product_name)
        return product if product else None

    def get_order_summary_by_date_range(self, start_date: datetime.date, end_date: datetime.date) -> Dict[str, Any]:
        """Retrieve a summary of orders within a given date range."""
        start_date_str = start_date.isoformat()
        end_date_str = end_date.isoformat()

        orders = self.order_repo.get_orders_by_date_range(start_date_str, end_date_str)
        summary = {
            "total_orders": len(orders),
            "total_revenue": 0,
            "average_order_value": 0,
            "order_count_by_customer": {},
            "product_sales_summary": {}
        }

        for order in orders:
            order_items = self.order_repo.get_order_items_by_order_id(order.order_id)
            total_value = sum(item.quantity * item.unit_price for item in order_items)
            summary["total_revenue"] += total_value

            customer_name = order.customer_name
            summary["order_count_by_customer"][customer_name] = summary["order_count_by_customer"].get(customer_name, 0) + 1

            for item in order_items:
                product_name = item.product_name
                quantity = item.quantity
                summary["product_sales_summary"][product_name] = summary["product_sales_summary"].get(product_name, 0) + quantity

        if orders:
            summary["average_order_value"] = summary["total_revenue"] / len(orders)

        return summary
