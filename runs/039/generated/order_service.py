"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Dict, List, Optional

from database import Database
from exceptions import (
    NotFoundError,
    OrderCreationFailedError,
    ValidationError,
)
from models import Order
from order_repository import OrderRepository
from product_repository import ProductRepository
from user_repository import UserRepository


class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)
        self.user_repo = UserRepository(db)

    def create_order(self, user_id: int, product_ids: List[int], quantity: int) -> Optional[Order]:
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError(f'User with id {user_id} not found')
        total_amount = 0.0
        for product_id in product_ids:
            product = self.product_repo.get_by_id(product_id)
            if not product:
                raise NotFoundError(f'Product with id {product_id} not found')
            if product.stock_quantity < quantity:
                raise ValidationError(f'Insufficient stock for product {product_id}. Current stock: {product.stock_quantity}, requested: {quantity}')
            total_amount += product.price * quantity
        order = Order(created_at=datetime.datetime.now(), id=None, status='pending', total_amount=total_amount, updated_at=datetime.datetime.now(), user_id=user_id)
        try:
            created_order = self.order_repo.create(order)
            return created_order
        except Exception as e:
            raise OrderCreationFailedError(f'Failed to create order: {str(e)}')

    def get_user_orders(self, user_id: int, status: Optional[str]=None) -> List[Order]:
        if status is None:
            return self.order_repo.get_orders_by_user_and_status(user_id, 'all')
        else:
            return self.order_repo.get_orders_by_user_and_status(user_id, status)

    def get_user_order_details(self, user_id: int) -> List[dict]:
        orders_with_details = self.user_repo.get_user_orders_with_product_details(user_id)
        return orders_with_details

    def export_user_orders_to_csv(self, user_id: int, file_path: str) -> None:
        rows = self.order_repo.list(user_id=user_id, )
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'user_id', 'status', 'total_amount',
                'created_at', 'updated_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.user_id, row.status, row.total_amount,
                    row.created_at, row.updated_at,
                ])

    def get_order_summary_by_status(self) -> Dict[str, int]:
        return self.order_repo.get_order_summary_by_status()

    def get_orders_by_date_range_and_status(self, start_date: datetime, end_date: datetime, status: str) -> List[Order]:
        return self.order_repo.get_orders_by_date_range_and_status(start_date, end_date, status)

    def get_orders_with_price_range(self, min_total: float, max_total: float, status: Optional[str]=None) -> List[Order]:
        if status is None:
            return self.order_repo.get_orders_with_status_and_price_range(min_total, max_total, 'all')
        else:
            return self.order_repo.get_orders_with_status_and_price_range(min_total, max_total, status)

