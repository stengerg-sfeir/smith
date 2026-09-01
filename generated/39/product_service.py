"""Service layer."""
from __future__ import annotations

import datetime
from typing import List

from database import Database
from models import Order, Product, User
from order_repository import OrderRepository
from product_repository import ProductRepository
from user_repository import UserRepository


class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)
        self.user_repo = UserRepository(db)

    def add_product(self, name: str, description: str, price: str, stock_quantity: int) -> None:
        product = Product(name=name, description=description, price=price, stock_quantity=stock_quantity, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def list_product(self, name: str, price: str, price_end: str, created_at: str, created_at_end: str) -> List[Product]:
        return self.product_repo.list(name=name, price=price, price_end=price_end, created_at=created_at, created_at_end=created_at_end)

    def update_product(self, id: int, name: str, description: str, price: str, stock_quantity: int) -> None:
        data = {k: v for k, v in {'name': name, 'description': description, 'price': price, 'stock_quantity': stock_quantity}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_product(self, id: int) -> None:
        return self.product_repo.delete(id)

    def add_user(self, email: str, password_hash: str, role: str) -> None:
        user = User(email=email, password_hash=password_hash, role=role, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.user_repo.create(user)

    def list_user(self, email: str, role: str, created_at: str, created_at_end: str) -> List[User]:
        return self.user_repo.list(email=email, role=role, created_at=created_at, created_at_end=created_at_end)

    def update_user(self, id: int, email: str, password_hash: str, role: str) -> None:
        data = {k: v for k, v in {'email': email, 'password_hash': password_hash, 'role': role}.items() if v is not None}
        return self.user_repo.update(id, data)

    def delete_user(self, id: int) -> None:
        return self.user_repo.delete(id)

    def list_order(self, user_id: str, status: str, created_at: str, created_at_end: str) -> List[Order]:
        return self.order_repo.list(user_id=user_id, status=status, created_at=created_at, created_at_end=created_at_end)

