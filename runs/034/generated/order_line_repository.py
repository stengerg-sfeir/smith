"""OrderLineRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import OrderLine


class OrderLineRepository:
    """SQLite repository for OrderLine over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order_line: OrderLine) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO order_lines (order_id, product_id, quantity, unit_price, total_price) VALUES (?, ?, ?, ?, ?)",
                (order_line.order_id, order_line.product_id, order_line.quantity, order_line.unit_price, order_line.total_price),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[OrderLine]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM order_lines WHERE id = ?", (id,)
            ).fetchone()
            return OrderLine(**dict(row)) if row else None

    def get_all(self) -> List[OrderLine]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM order_lines ORDER BY id"
            ).fetchall()
            return [OrderLine(**dict(r)) for r in rows]

    def list(self, order_id: Optional[Any] = None, product_id: Optional[Any] = None, quantity: Optional[Any] = None, unit_price: Optional[Any] = None) -> List[OrderLine]:
        with self.db.connect() as conn:
            query = "SELECT * FROM order_lines WHERE 1=1"
            params: List[Any] = []
            if order_id is not None:
                query += ' AND order_id = ?'
                params.append(order_id)
            if product_id is not None:
                query += ' AND product_id = ?'
                params.append(product_id)
            if quantity is not None:
                query += ' AND quantity = ?'
                params.append(quantity)
            if unit_price is not None:
                query += ' AND unit_price = ?'
                params.append(unit_price)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [OrderLine(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['order_id', 'product_id', 'quantity', 'unit_price', 'total_price']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE order_lines SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM order_lines WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def create_order_line_with_validation(self, order_id: int, product_id: int, quantity: int, unit_price: float) -> bool:
        return self.list(
            order_id=order_id,
            product_id=product_id,
            quantity=quantity,
            unit_price=unit_price,
        )

    def get_order_line_by_id_with_order(self, order_line_id: int) -> OrderLineWithOrder:
        return None

    def list_order_lines_by_order_id(self, order_id: int, product_id: int) -> list[OrderLineWithOrder]:
        return self.list(
            order_id=order_id,
            product_id=product_id,
        )

    def get_order_line_total_by_product(self, product_id: int, start_date: str, end_date: str) -> float:
        with self.db.connect() as conn:
            cursor = conn.execute('SELECT total_price FROM order_lines WHERE product_id = ?', (product_id,))
            rows = cursor.fetchall()
            total = 0.0
            for row in rows:
                total += row[0]
            return total

    def validate_order_line_data(self, order_line_data: dict) -> bool:
        required_fields = ['order_id', 'product_id', 'quantity', 'total_price', 'unit_price']
        for field in required_fields:
            if field not in order_line_data:
                return False
        try:
            order_id = int(order_line_data['order_id'])
            product_id = int(order_line_data['product_id'])
            quantity = int(order_line_data['quantity'])
            total_price = float(order_line_data['total_price'])
            unit_price = float(order_line_data['unit_price'])
        except (ValueError, TypeError):
            return False
        if quantity <= 0:
            return False
        if total_price <= 0 or unit_price <= 0:
            return False
        if abs(total_price - quantity * unit_price) > 1e-06:
            return False
        return True

