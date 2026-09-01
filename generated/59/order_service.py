"""Service layer."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from customer_repository import CustomerRepository
from database import Database
from discount_repository import DiscountRepository
from exceptions import (
    InvalidDiscountError,
    NotFoundError,
    OrderCancellationError,
)
from models import Customer, Discount, Order, Product
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
        order = self.order_repo.get_by_id(id)
        if not order:
            raise NotFoundError(f'Order with id {id} not found')
        discount = self.discount_repo.get_by_id(id)
        if not discount:
            raise NotFoundError(f'Discount with id {id} not found')
        order_total = order.total_amount
        if not self.discount_repo.validate_discount_for_order(order_total, discount.id):
            raise InvalidDiscountError(f'Discount {discount.name} is not valid for order total {order_total}')
        order_data = {'discount_id': discount.id}
        self.order_repo.update(order.id, order_data)

    def cancel_order(self, order_id: int) -> None:
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        if order.status == 'cancelled':
            raise OrderCancellationError(f'Order {order_id} is already cancelled')
        order.status = 'cancelled'
        self.order_repo.update(order.id, {'status': 'cancelled'})

    def restore_order(self, order_id: int) -> None:
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        if order.status != 'cancelled':
            raise OrderCancellationError(f'Order {order_id} is not cancelled and cannot be restored')
        order.status = 'pending'
        self.order_repo.update(order.id, {'status': 'pending'})

    def list_order(self, order_id: Optional[int] = None, status: Optional[str] = None) -> List[Order]:
        if order_id is not None:
            return [self.order_repo.get_by_id(order_id)]
        return self.order_repo.list(status=status)

    def get_order_report(self, order_id: int) -> Dict[str, Any]:
        order = self.order_repo.get_by_id(order_id)
        if not order:
            raise NotFoundError(f'Order with id {order_id} not found')
        order_data = {
            'id': order.id,
            'customer_id': order.customer_id,
            'order_date': order.order_date,
            'status': order.status,
            'total_amount': order.total_amount,
            'discount_id': order.discount_id,
            'tax_rate': order.tax_rate
        }
        return order_data

    def get_customer_report(self, customer_id: int) -> Dict[str, Any]:
        customer = self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundError(f'Customer with id {customer_id} not found')
        orders = self.order_repo.list(customer_id=customer_id)
        total_spent = sum(order.total_amount for order in orders)
        order_count = len(orders)
        return {
            'id': customer.id,
            'name': customer.name,
            'email': customer.email,
            'phone': customer.phone,
            'total_orders': order_count,
            'total_spent': total_spent
        }

    def add_discount(self, name: str, discount_type: str, value: str, min_order_total: str) -> None:
        discount = Discount(name=name, discount_type=discount_type, value=value, min_order_total=min_order_total)
        return self.discount_repo.create(discount)

    def apply_order(self, order_data: Dict[str, Any]) -> None:
        customer_id = order_data['customer_id']
        order_date = order_data['order_date']
        status = order_data['status']
        total_amount = order_data['total_amount']
        discount_id = order_data.get('discount_id')
        tax_rate = order_data.get('tax_rate')

        # Validate customer exists
        customer = self.customer_repo.get_by_id(customer_id)
        if not customer:
            raise NotFoundError(f'Customer with id {customer_id} not found')

        # Validate discount if provided
        if discount_id:
            discount = self.discount_repo.get_by_id(discount_id)
            if not discount:
                raise NotFoundError(f'Discount with id {discount_id} not found')
            if not self.discount_repo.validate_discount_for_order(total_amount, discount.id):
                raise InvalidDiscountError(f'Discount {discount.name} is not valid for order total {total_amount}')

        # Apply tax
        tax_amount = self.tax_repo.calculate_tax(total_amount, tax_rate)
        final_total = total_amount + tax_amount

        # Create order
        order = Order(
            customer_id=customer_id,
            order_date=order_date,
            status=status,
            total_amount=str(final_total),
            discount_id=discount_id,
            tax_rate=tax_rate
        )
        self.order_repo.create(order)
