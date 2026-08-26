"""Service layer."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import (
    InvalidOrderLineException,
    OrderCreationFailedException,
    ValidationError,
)
from models import Order, OrderLine
from order_repository import OrderRepository


class OrderCreationService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.order_repo = OrderRepository(db)

    def create_order_with_lines(self, order_data: Dict[str, Any], order_lines: List[Dict[str, Any]]) -> Optional[Order]:
        if not self.validate_order_lines(order_lines):
            raise ValidationError('Invalid order lines provided')
        try:
            order = Order(created_at=order_data.get('created_at'), id=order_data.get('id'), status=order_data.get('status', 'pending'), updated_at=order_data.get('updated_at'))
            order_id = self.order_repo.create(order)
            if not order_id:
                raise OrderCreationFailedException('Failed to create order')
            for line in order_lines:
                product_id = line.get('product_id')
                quantity = line.get('quantity')
                unit_price = line.get('unit_price')
                if not self.create_order_line_with_validation(order_id, product_id, quantity, unit_price):
                    raise OrderCreationFailedException('Failed to create at least one order line')
            order_with_lines = self.order_repo.get_order_by_id_with_lines(order_id)
            if not order_with_lines:
                raise OrderCreationFailedException('Order not found after creation')
            return order_with_lines
        except Exception:
            if hasattr(self.order_repo, 'delete') and self.order_repo.delete(order_id):
                pass
            raise

    def validate_order_lines(self, order_lines: List[Dict[str, Any]]) -> bool:
        for line in order_lines:
            product_id = line.get('product_id')
            quantity = line.get('quantity')
            unit_price = line.get('unit_price')
            if not all([product_id, quantity, unit_price]):
                return False
            if not isinstance(quantity, int) or quantity <= 0:
                return False
            if not isinstance(unit_price, (int, float)) or unit_price <= 0:
                return False
        return True

    def create_order_line_with_validation(self, order_id: int, product_id: int, quantity: int, unit_price: float) -> bool:
        try:
            order_line_data = {'order_id': order_id, 'product_id': product_id, 'quantity': quantity, 'unit_price': unit_price}
            if not self.order_repo.validate_order_line_data(order_line_data):
                raise InvalidOrderLineException('Invalid order line data')
            order_line = OrderLine(
                order_id=order_id,
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price
            )
            self.order_repo.create_order_line(order_line)
            return True
        except Exception:
            raise

    def get_order_line_total_by_product(self, order_id: int, product_id: int) -> int:
        """Calculate the total price for a product in an order."""
        total = 0
        # Assuming order_lines are stored in a table with order_id, product_id, quantity, unit_price
        cursor = self.db.get_cursor()
        cursor.execute(
            "SELECT quantity * unit_price FROM order_lines WHERE order_id = ? AND product_id = ?",
            (order_id, product_id)
        )
        row = cursor.fetchone()
        if row:
            total = int(row[0])
        return total

    def list_order_lines_by_order_id(self, order_id: int) -> List[Dict[str, Any]]:
        """Retrieve all order lines for a given order ID."""
        lines = []
        cursor = self.db.get_cursor()
        cursor.execute(
            "SELECT product_id, quantity, unit_price FROM order_lines WHERE order_id = ?",
            (order_id,)
        )
        rows = cursor.fetchall()
        for row in rows:
            lines.append({
                'product_id': row[0],
                'quantity': row[1],
                'unit_price': row[2]
            })
        return lines
