"""Service layer."""
from __future__ import annotations

from typing import List

from customer_repository import CustomerRepository
from database import Database
from discount_repository import DiscountRepository
from exceptions import (
    InvalidDiscountError,
    NotFoundError,
)
from models import Customer, Order, Product
from order_line_repository import OrderLineRepository
from order_repository import OrderRepository
from product_repository import ProductRepository
from tax_repository import TaxRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.discount_repo = DiscountRepository(db)
        self.order_repo = OrderRepository(db)
        self.order_line_repo = OrderLineRepository(db)
        self.product_repo = ProductRepository(db)
        self.tax_repo = TaxRepository(db)

    def add_customer(self, name: str, email: str, phone: str) -> None:
        customer = Customer(name=name, email=email, phone=phone)
        return self.customer_repo.create(customer)

    def add_product(self, name: str, description: str, price: str, stock_quantity: int, category: str) -> None:
        product = Product(name=name, description=description, price=price, stock_quantity=stock_quantity, category=category)
        return self.product_repo.create(product)

    def list_product(self, name: str, category: str, price_min: str, price_max: str, stock_min: str, stock_max: str) -> List[Product]:
        return self.product_repo.list(name=name, category=category, price_min=price_min, price_max=price_max, stock_min=stock_min, stock_max=stock_max)

    def add_order(self, customer_id: int, order_date: str, status: str, total_amount: str, discount_id: int, tax_rate: str) -> None:
        order = Order(customer_id=customer_id, order_date=order_date, status=status, total_amount=total_amount, discount_id=discount_id, tax_rate=tax_rate)
        return self.order_repo.create(order)

    def apply_discount(self, id: int) -> None:
        """Apply a discount to an order by its ID."""
        order = self.order_repo.get_by_id(id)
        if not order:
            raise NotFoundError(f'Order with ID {id} not found.')
        discount = self.discount_repo.get_by_id(id)
        if not discount:
            raise NotFoundError(f'Discount with ID {id} not found.')
        if not self.discount_repo.validate_discount_for_order(order.total_amount, discount.id):
            raise InvalidDiscountError(f'Discount {discount.name} is not valid for order total {order.total_amount}.')
        order_data = {'discount_id': discount.id, 'total_amount': order.total_amount}
        self.order_repo.update(order.id, order_data)
