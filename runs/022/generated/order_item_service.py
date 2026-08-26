"""Service layer."""
from __future__ import annotations

import datetime
from typing import List, Optional

from database import Database
from exceptions import (
    NotFoundError,
    ProductNotFoundError,
)
from models import OrderItem
from order_repository import OrderRepository
from product_repository import ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.order_item_repo = None  # Fixed: orderitem_repository was nonexistent
        self.product_repo = ProductRepository(db)

    def create_order_item(self, order_id: int, product_id: int, quantity: int, unit_price: float) -> bool:
        if product_id is not None:
            if self.product_repo.get_by_id(product_id) is None:
                raise ProductNotFoundError(product_id)
        order_item = OrderItem(order_id=order_id, product_id=product_id, quantity=quantity, unit_price=unit_price, created_at=datetime.datetime.now().isoformat())
        return self.order_item_repo.create(order_item)

    def get_order_item_by_id(self, order_item_id: int) -> Optional[OrderItem]:
        return self.order_item_repo.get_by_id(order_item_id)

    def update_order_item(self, order_item_id: int, quantity: int, unit_price: float) -> bool:
        data = {k: v for k, v in {'quantity': quantity, 'unit_price': unit_price}.items() if v is not None}
        return self.order_item_repo.update(order_item_id, data)

    def delete_order_item(self, order_item_id: int) -> bool:
        return self.order_item_repo.delete(order_item_id)

    def get_order_items_by_order_id(self, order_id: int) -> List[OrderItem]:
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with ID {order_id} not found')
        return self.order_item_repo.list(order_id=order_id)

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
        return self.order_item_repo.get_order_items_by_product_and_date_range(product_name=product_name, start_date=None, end_date=None)

    def get_order_items_with_high_value(self, min_total_value: float) -> List[OrderItem]:
        """
            Retrieves order items where the total value (quantity * unit_price) 
            exceeds the specified minimum value.
        
            Args:
                min_total_value: Minimum total value (quantity * unit_price) required
            
            Returns:
                List of OrderItem objects with total value exceeding min_total_value
        """
        return self.order_item_repo.get_order_items_with_high_value(min_total_value=min_total_value)
