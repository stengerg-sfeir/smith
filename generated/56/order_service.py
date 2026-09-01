"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    AtomicOperationFailedError,
    InvalidOrderStatusError,
    OrderNotFoundError,
)
from models import Customer, Product
from order_repository import OrderRepository
from product_repository import ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)

    def add_customer(self, name: str, email: str) -> bool:
        customer = Customer(name=name, email=email)
        return self.customer_repo.create(customer)

    def add_product(self, name: str, description: Optional[str] = None, price: str = None, stock_quantity: int = None) -> bool:
        product = Product(name=name, description=description, price=price, stock_quantity=stock_quantity, created_at=datetime.datetime.now().isoformat())
        return self.product_repo.create(product)

    def search_product(self, term: str) -> list[dict]:
        """
            Search for products by name or category using the product repository's search functionality.
            Filters are applied based on the provided term, with no price or category constraints.
            """
        return self.product_repo.search_products_with_filters(query=term, min_price=None, max_price=None, category=None, in_stock_only=None)

    def filter_product(self, id: int) -> dict:
        results = []
        groups = {}
        for row in self.product_repo.list():
            key = (row.name)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'name': key[0],
                    'count': len(group),
                })
        return results

    def cancel_product(self, id: int) -> bool:
        """
            Cancel a product order by ID. This method attempts to cancel the order
            if it exists and is in a cancellable status (e.g., 'pending' or 'created').
        
            Args:
                id: The ID of the order to cancel
            
            Returns:
                True if cancellation was successful, False otherwise
            """
        try:
            order = self.order_repo.get_by_id(id)
            if not order:
                raise OrderNotFoundError(f'Order with ID {id} not found')
            if order.status not in ['pending', 'created']:
                raise InvalidOrderStatusError(f'Order with ID {id} cannot be cancelled. Current status: {order.status}')
            success = self.order_repo.cancel_order(id)
            if success:
                pass
            return success
        except Exception as e:
            raise AtomicOperationFailedError(f'Failed to cancel order: {str(e)}')

    def list_customer(self) -> list[dict]:
        return self.customer_repo.list()

    def list_product(self, name: Optional[str] = None, price: Optional[str] = None, stock_quantity: Optional[str] = None) -> list[dict]:
        results = {}
        for row in self.product_repo.list(name=name, price=price, stock_quantity=stock_quantity):
            key = row.name
            results[key] = results.get(key, 0) + row.price
        return results

    def list_order(self, status: Optional[str] = None, total_amount: Optional[str] = None, created_at: Optional[str] = None) -> list[dict]:
        rows = self.order_repo.list(status=status, total_amount=total_amount, created_at=created_at)
        total = sum(e.total_amount for e in rows)
        return {'total_order_value': total}

    def customers_customer(self, id: int) -> dict:
        results = []
        groups = {}
        for row in self.customer_repo.list():
            key = (row.email)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'email': key[0],
                    'count': len(group),
                })
        return results

