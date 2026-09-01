"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from category_repository import CategoryRepository
from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    CategoryNotFoundError,
    CustomerNotFoundError,
    InvalidOrderStatusError,
    InvoiceNotFoundError,
    OrderNotFoundError,
)
from invoice_repository import InvoiceRepository
from models import Category, Customer, Order, Product
from order_repository import OrderRepository
from product_repository import ProductRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.category_repo = CategoryRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.invoice_repo = InvoiceRepository(db)
        self.order_repo = OrderRepository(db)
        self.product_repo = ProductRepository(db)

    def add_customer(self, name: str, email: str, phone: str) -> None:
        customer = Customer(name=name, email=email, phone=phone)
        return self.customer_repo.create(customer)

    def list_customer(self, name: Optional[str] = None, email: Optional[str] = None, phone: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.customer_repo.list(name=name, email=email, phone=phone):
            key = (row.name, row.email, row.phone)
            groups[key] = groups.get(key, 0) + 1
        for key, count in groups.items():
            results.append({
                    'name': key[0],
                    'email': key[1],
                    'phone': key[2],
                    'count': count,
                })
        return results

    def search_customer(self, term: str) -> List[Dict[str, Any]]:
        """Search customers by email or name."""
        results = self.customer_repo.search_orders_by_customer_email(email=term, status_filter=None, date_from=None, date_to=None)
        return [{'id': customer.id, 'name': customer.name, 'email': customer.email, 'phone': customer.phone} for customer in results]

    def add_product(self, name: str, description: Optional[str] = None, price: str = None, stock_quantity: int = None, category_id: int = None) -> None:
        if category_id is not None:
            if self.category_repo.get_by_id(category_id) is None:
                raise CategoryNotFoundError(category_id)
        product = Product(name=name, description=description, price=price, stock_quantity=stock_quantity, category_id=category_id)
        return self.product_repo.create(product)

    def list_product(self, name: Optional[str] = None, category_id: Optional[str] = None, price: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.product_repo.list(name=name, category_id=category_id, price=price):
            key = (row.name, row.category_id, row.price)
            groups[key] = groups.get(key, 0) + 1
        for key, count in groups.items():
            results.append({
                    'name': key[0],
                    'category_id': key[1],
                    'price': key[2],
                    'count': count,
                })
        return results

    def search_category(self, term: str) -> List[Dict[str, Any]]:
        """Search categories by name."""
        results = self.category_repo.list(name__contains=term)
        return [{'id': category.id, 'name': category.name} for category in results]

    def add_category(self, name: str) -> None:
        category = Category(name=name)
        return self.category_repo.create(category)

    def list_order(self, customer_id: Optional[str] = None, status: Optional[str] = None, created_at: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.order_repo.list(customer_id=customer_id, status=status, created_at=created_at):
            key = (row.customer_id, row.status)
            groups[key] = groups.get(key, 0) + 1
        for key, count in groups.items():
            results.append({
                    'customer_id': key[0],
                    'status': key[1],
                    'count': count,
                })
        return results

    def confirm_invoice(self, id: int) -> None:
        """Confirm an invoice by updating its status to 'confirmed'."""
        invoice = self.invoice_repo.get_by_id(id)
        if not invoice:
            raise InvoiceNotFoundError(f'Invoice with id {id} not found')
        invoice.status = 'confirmed'
        self.invoice_repo.update(id, {'status': 'confirmed'})

    def cancel_order(self, id: int) -> None:
        """Cancel an order by updating its status to 'cancelled'."""
        order = self.order_repo.get_by_id(id)
        if not order:
            raise OrderNotFoundError(f'Order with id {id} not found')
        if order.status not in ['pending', 'processing']:
            raise InvalidOrderStatusError(f'Order with id {id} cannot be cancelled. Current status is {order.status}')
        order.status = 'cancelled'
        self.order_repo.update(id, {'status': 'cancelled'})

    def list_invoice(self, order_id: Optional[str] = None, total_amount: Optional[str] = None) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.invoice_repo.list(order_id=order_id, total_amount=total_amount):
            key = (row.order_id, row.total_amount)
            groups[key] = groups.get(key, 0) + 1
        for key, count in groups.items():
            results.append({
                    'order_id': key[0],
                    'total_amount': key[1],
                    'count': count,
                })
        return results

    def add_order(self, customer_id: int, status: str) -> None:
        if customer_id is not None:
            if self.customer_repo.get_by_id(customer_id) is None:
                raise CustomerNotFoundError(customer_id)
        order = Order(customer_id=customer_id, status=status, created_at=datetime.datetime.now().isoformat(), updated_at=datetime.datetime.now().isoformat())
        return self.order_repo.create(order)

