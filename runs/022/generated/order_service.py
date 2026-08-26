"""Service layer."""
from __future__ import annotations

import datetime
from typing import Dict, List, Optional

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
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f"Order with ID {order_id} not found")
        total = 0.0
        for item in order.items:
            product = self.product_repo.get_product_by_name(item.product_name)
            if product:
                total += product.price * item.quantity
        return total

    def get_orders_by_customer(self, customer_name: str) -> List[Order]:
        """Retrieve all orders for a given customer name."""
        return self.order_repo.get_order_with_items_by_customer(customer_name)

    def get_order_items_by_product(self, product_name: str, min_quantity: int) -> List[OrderItem]:
        """
            Retrieves order items for a specific product with minimum quantity requirement.
        
            Args:
                product_name: Name of the product to filter by
                min_quantity: Minimum quantity required in the order item
            
            Returns:
                List of OrderItem objects matching the criteria
            """
        product = self.product_repo.get_product_by_name(product_name)
        if not product:
            raise ProductNotFoundError(f"Product '{product_name}' not found")
        return self.order_repo.get_order_items_by_product_and_date_range(product_name=product_name, start_date=None, end_date=None)

    def get_orders_with_high_value_items(self, min_total_amount: float) -> List[Order]:
        """Retrieve orders that contain items with total value exceeding min_total_amount."""
        return self.order_repo.get_orders_with_high_value_items(min_total_amount)

    def get_order_summary_by_date_range(self, start_date: datetime, end_date: datetime) -> Dict[str, float]:
        """Returns a summary of order values by date range."""
        return self.order_repo.get_order_summary_by_date_range(start_date, end_date)

    def get_most_popular_product(self) -> Optional[Product]:
        """Returns the most popular product based on total quantity sold."""
        # Aggregate total quantities sold per product
        product_quantity_map = {}
        for order in self.order_repo.get_all_orders():
            for item in order.items:
                product_name = item.product_name
                if product_name not in product_quantity_map:
                    product_quantity_map[product_name] = 0
                product_quantity_map[product_name] += item.quantity

        if not product_quantity_map:
            return None

        # Find product with highest total quantity sold
        most_popular_product_name = max(product_quantity_map, key=product_quantity_map.get)
        product = self.product_repo.get_product_by_name(most_popular_product_name)
        return product if product else None
