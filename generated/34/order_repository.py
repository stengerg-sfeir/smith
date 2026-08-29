"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Order


class OrderRepository:
    """SQLite repository for Order over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order: Order) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders (created_at, updated_at, status) VALUES (?, ?, ?)",
                (order.created_at, order.updated_at, order.status),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Order]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (id,)
            ).fetchone()
            return Order(**dict(row)) if row else None

    def get_all(self) -> List[Order]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY id"
            ).fetchall()
            return [Order(**dict(r)) for r in rows]

    def list(self, status: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if status is not None:
                query += ' AND status = ?'
                params.append(status)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['created_at', 'updated_at', 'status']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE orders SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM orders WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def create_order_with_lines(self, order_data: dict, order_lines: list[dict]) -> None:
        with self.db.connect() as conn:
            conn.execute('INSERT INTO orders (created_at, id, status, updated_at) VALUES (?, ?, ?, ?)', (order_data['created_at'], order_data['id'], order_data['status'], order_data['updated_at']))
            for line in order_lines:
                conn.execute('INSERT INTO order_lines (order_id, product_id, quantity, total_price, unit_price) VALUES (?, ?, ?, ?, ?)', (line['order_id'], line['product_id'], line['quantity'], line['total_price'], line['unit_price']))
            conn.commit()

    def get_order_by_id_with_lines(self, order_id: int) -> OrderWithLines:
        return None

    def list_orders_with_filters(self, status: str, created_after: datetime, created_before: datetime, product_id: int) -> list[OrderWithLines]:
        return []

    def get_order_total_count(self, status: str, created_after: datetime, created_before: datetime) -> int:
        return 0

    def generate_order_report_by_product(self, start_date: datetime, end_date: datetime) -> dict:
        return {}

    def validate_order_lines(self, order_lines: list[dict]) -> bool:
        if not order_lines:
            return False
        for line in order_lines:
            if not all((k in line for k in ['product_id', 'quantity', 'total_price', 'unit_price'])):
                return False
            if not isinstance(line['quantity'], int) or line['quantity'] <= 0:
                return False
            if not isinstance(line['unit_price'], (int, float)) or line['unit_price'] <= 0:
                return False
            if not isinstance(line['total_price'], (int, float)) or line['total_price'] <= 0:
                return False
            if line['total_price'] != line['quantity'] * line['unit_price']:
                return False
        return True

