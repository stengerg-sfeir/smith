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

    def create_order_line_with_order(self, order_id: int, product_id: int, quantity: int, unit_price: float) -> None:
        return self.list(
            order_id=order_id,
            product_id=product_id,
            quantity=quantity,
            unit_price=unit_price,
        )

    def get_order_line_by_id_with_order(self, order_line_id: int) -> OrderLineWithOrder:
        return None

    def list_order_lines_with_filters(self, order_id: int, product_id: int, quantity_min: int, quantity_max: int, unit_price_min: float, unit_price_max: float) -> list[OrderLineWithOrder]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM order_lines r JOIN orders o ON r.order_id = o.id WHERE o.id = ?",
                (order_id,)
            ).fetchall()
            return [OrderLine(**dict(r)) for r in rows]

    def get_order_line_total_count(self, order_id: int, product_id: int) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM order_lines WHERE order_id = ? AND product_id = ?",
                (order_id, product_id)
            ).fetchone()
            return int(row["n"])

    def validate_order_line_data(self, order_line_data: dict) -> bool:
        required_fields = ['order_id', 'product_id', 'quantity', 'total_price', 'unit_price']
        for field in required_fields:
            if field not in order_line_data or order_line_data[field] is None:
                return False
        if not isinstance(order_line_data['quantity'], (int, float)) or order_line_data['quantity'] <= 0:
            return False
        if not isinstance(order_line_data['total_price'], (int, float)) or order_line_data['total_price'] <= 0:
            return False
        if not isinstance(order_line_data['unit_price'], (int, float)) or order_line_data['unit_price'] <= 0:
            return False
        return True

    def get_order_line_summary_by_product(self, period_start: str, period_end: str) -> dict[str, float]:
        with self.db.connect() as conn:
            query = '\n                SELECT ol.product_id, SUM(ol.quantity * ol.unit_price) AS total_revenue\n                FROM order_lines ol\n                WHERE ol.order_id IN (\n                    SELECT o.id \n                    FROM orders o \n                    WHERE o.created_at BETWEEN ? AND ?\n                )\n                GROUP BY ol.product_id\n            '
            rows = conn.execute(query, (period_start, period_end)).fetchall()
            result = {}
            for row in rows:
                result[str(row[0])] = float(row[1])
            return result

