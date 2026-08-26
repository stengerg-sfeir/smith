"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Order, OrderLine


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
            cursor = conn.cursor()
            cursor.execute('INSERT INTO orders (created_at, id, status, updated_at) VALUES (?, ?, ?, ?)', (order_data.get('created_at'), order_data.get('id'), order_data.get('status'), order_data.get('updated_at')))
            order_id = cursor.lastrowid
            for line in order_lines:
                cursor.execute('INSERT INTO order_lines (order_id, product_id, quantity, total_price, unit_price) VALUES (?, ?, ?, ?, ?)', (order_id, line.get('product_id'), line.get('quantity'), line.get('total_price'), line.get('unit_price')))
            conn.commit()

    def get_order_by_id_with_lines(self, order_id: int) -> Order:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT o.id, o.created_at, o.status, o.updated_at, ol.product_id, ol.quantity, ol.total_price, ol.unit_price FROM orders o LEFT JOIN order_lines ol ON o.id = ol.order_id WHERE o.id = ?', (order_id,))
            rows = cursor.fetchall()
            order_lines = []
            for row in rows:
                order_lines.append(OrderLine(product_id=row[4], quantity=row[5], total_price=row[6], unit_price=row[7]))
            order = Order(id=row[0], created_at=row[1], status=row[2], updated_at=row[3])
            return order

    def list_orders_with_filters(self, status: str, created_after: datetime, created_before: datetime, product_id: int) -> list[OrderWithLines]:
        return self.list(
            status=status,
        )

    def get_order_total_count(self, status: str, created_after: datetime, created_before: datetime) -> int:
        return self.list(
            status=status,
        )

    def generate_order_report_by_product(self, start_date: str, end_date: str) -> dict:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT ol.product_id, SUM(ol.quantity) as total_quantity, SUM(ol.total_price) as total_revenue FROM order_lines ol WHERE ol.order_id IN (    SELECT o.id FROM orders o     WHERE o.created_at BETWEEN ? AND ?) GROUP BY ol.product_id', (start_date, end_date))
            rows = cursor.fetchall()
            report = {}
            for row in rows:
                report[row[0]] = {'total_quantity': row[1], 'total_revenue': row[2]}
            return report

    def validate_order_lines(self, order_lines: list[dict]) -> bool:
        for line in order_lines:
            if not line.get('product_id') or not line.get('quantity') or (not line.get('unit_price')):
                return False
            if not isinstance(line.get('quantity'), int) or line.get('quantity') <= 0:
                return False
            if not isinstance(line.get('unit_price'), (int, float)) or line.get('unit_price') <= 0:
                return False
            if not isinstance(line.get('total_price'), (int, float)) or line.get('total_price') <= 0:
                return False
            expected_total = line['quantity'] * line['unit_price']
            if abs(line['total_price'] - expected_total) > 1e-06:
                return False
        return True

