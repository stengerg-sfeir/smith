"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from database import Database
from exceptions import (
    InvalidOrderLineException,
    OrderCreationFailedException,
    ValidationError,
)
from models import Order, OrderLine
from order_line_repository import OrderLineRepository
from order_repository import OrderRepository


class OrderService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)
        self.order_line_repo = OrderLineRepository(db)

    def create_order_with_lines(self, order_data: Dict[str, Any], order_lines: List[Dict[str, Any]]) -> Optional[OrderWithLines]:
        if not self.validate_order_lines(order_lines):
            raise ValidationError('Invalid order lines provided')
        order = Order(created_at=order_data.get('created_at'), id=order_data.get('id'), status=order_data.get('status'), updated_at=order_data.get('updated_at'))
        try:
            order_id = self.order_repo.create(order)
            if not order_id:
                raise OrderCreationFailedException('Failed to create order')
            for line_data in order_lines:
                order_line = OrderLine(id=None, order_id=order_id, product_id=line_data.get('product_id'), quantity=line_data.get('quantity'), unit_price=line_data.get('unit_price'), total_price=line_data.get('total_price'))
                if not self.validate_order_line_data(line_data):
                    raise InvalidOrderLineException('Invalid order line data')
                self.order_line_repo.create_order_line_with_validation(order_id, line_data['product_id'], line_data['quantity'], line_data['unit_price'])
        except Exception as e:
            self.order_repo.delete(order_id)
            raise e
        return self.get_order_by_id_with_lines(order_id)

    def validate_order_lines(self, order_lines: List[Dict[str, Any]]) -> bool:
        for line in order_lines:
            if not self.validate_order_line_data(line):
                return False
        return True

    def get_order_by_id_with_lines(self, order_id: int) -> Optional[OrderWithLines]:
        try:
            order_with_lines = self.order_repo.get_order_by_id_with_lines(order_id)
            return order_with_lines
        except Exception as e:
            raise ValidationError(f'Failed to retrieve order: {str(e)}')

    def list_orders_with_filters(self, status: str, created_after: datetime, created_before: datetime, product_id: int) -> List[OrderWithLines]:
        try:
            orders = self.order_repo.list_orders_with_filters(status, created_after, created_before, product_id)
            return orders
        except Exception as e:
            raise ValidationError(f'Failed to list orders with filters: {str(e)}')

    def get_order_total_count(self, status: str, created_after: datetime, created_before: datetime) -> int:
        try:
            count = self.order_repo.get_order_total_count(status, created_after, created_before)
            return count
        except Exception as e:
            raise ValidationError(f'Failed to get order total count: {str(e)}')

    def generate_order_report_by_product(self, start_date: datetime, end_date: datetime) -> dict:
        try:
            report = self.order_repo.generate_order_report_by_product(start_date, end_date)
            return report
        except Exception as e:
            raise ValidationError(f'Failed to generate order report: {str(e)}')

    def validate_order_line_data(self, order_line_data: Dict[str, Any]) -> bool:
        required_fields = ['product_id', 'quantity', 'unit_price']
        for field in required_fields:
            if field not in order_line_data or order_line_data[field] is None:
                return False
        quantity = order_line_data.get('quantity')
        unit_price = order_line_data.get('unit_price')
        if not isinstance(quantity, (int, float)) or quantity <= 0:
            return False
        if not isinstance(unit_price, (int, float)) or unit_price <= 0:
            return False
        total_price = order_line_data.get('total_price')
        if total_price is not None:
            expected_total = quantity * unit_price
            if abs(total_price - expected_total) > 1e-06:
                return False
        return True

