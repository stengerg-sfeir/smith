"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import List, Optional

from database import Database
from exceptions import (
    NotFoundError,
    ValidationError,
)
from models import Order, User
from order_repository import OrderRepository
from product_repository import ProductRepository
from user_repository import UserRepository


class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)
        self.user_repo = UserRepository(db)

    def create_user(self, email: str, password_hash: str, role: str) -> Optional[User]:
        user = User(email=email, password_hash=password_hash, role=role, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.user_repo.create(user)

    def get_user_orders(self, user_id: int, status: str) -> List[Order]:
        """
            Retrieve orders for a specific user with a given status.
            """
        try:
            return self.user_repo.get_user_orders_by_status(user_id, status)
        except Exception as e:
            raise NotFoundError(f'User or orders not found for user_id={user_id}, status={status}') from e

    def get_user_order_details(self, user_id: int) -> List[dict]:
        results = {}
        for row in self.order_repo.list(user_id=user_id):
            key = row.status
            results[key] = results.get(key, 0) + row.total_amount
        return results

    def get_user_with_most_orders(self) -> Optional[User]:
        """
            Retrieve the user with the highest number of orders.
            """
        try:
            return self.user_repo.get_user_with_most_orders()
        except Exception as e:
            raise NotFoundError('Could not retrieve user with most orders') from e

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

    def validate_user_permissions(self, user_role: str, action: str) -> bool:
        """
            Validate if a user with the given role has permission to perform the specified action.
            """
        allowed_actions = {'admin': ['create_order', 'view_all_orders', 'manage_products', 'view_sales_report'], 'manager': ['view_all_orders', 'view_sales_report'], 'user': ['view_own_orders']}
        action_lower = action.lower()
        if user_role not in allowed_actions:
            return False
        if action_lower in allowed_actions[user_role]:
            return True
        return False

    def get_active_user_count(self) -> int:
        """
            Get the count of active users.
            """
        try:
            return self.user_repo.get_active_products_count()
        except Exception as e:
            raise ValidationError('Failed to retrieve active user count') from e

