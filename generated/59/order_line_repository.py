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
                "INSERT INTO orderlines (order_id, product_id, quantity, unit_price, line_total) VALUES (?, ?, ?, ?, ?)",
                (order_line.order_id, order_line.product_id, order_line.quantity, order_line.unit_price, order_line.line_total),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[OrderLine]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM orderlines WHERE id = ?", (id,)
            ).fetchone()
            return OrderLine(**dict(row)) if row else None

    def get_all(self) -> List[OrderLine]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orderlines ORDER BY id"
            ).fetchall()
            return [OrderLine(**dict(r)) for r in rows]

    def list(self, order_id: Optional[Any] = None, product_id: Optional[Any] = None, max_price: Optional[Any] = None, max_quantity: Optional[Any] = None, min_price: Optional[Any] = None, min_quantity: Optional[Any] = None) -> List[OrderLine]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orderlines WHERE 1=1"
            params: List[Any] = []
            if order_id is not None:
                query += ' AND order_id = ?'
                params.append(order_id)
            if product_id is not None:
                query += ' AND product_id = ?'
                params.append(product_id)
            if max_price is not None:
                query += ' AND unit_price <= ?'
                params.append(max_price)
            if max_quantity is not None:
                query += ' AND quantity <= ?'
                params.append(max_quantity)
            if min_price is not None:
                query += ' AND unit_price >= ?'
                params.append(min_price)
            if min_quantity is not None:
                query += ' AND quantity >= ?'
                params.append(min_quantity)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [OrderLine(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['order_id', 'product_id', 'quantity', 'unit_price', 'line_total']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        sets_str = ', '.join([f"{k} = ?" for k in sets])
        params = list(data[k] for k in sets)
        params.append(id)
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(f"UPDATE orderlines SET {sets_str} WHERE id = ?", params)
            conn.commit()
            return cur.rowcount > 0
