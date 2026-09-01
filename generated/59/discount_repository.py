"""DiscountRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Discount


class DiscountRepository:
    """SQLite repository for Discount over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, discount: Discount) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO discounts (name, type, value, min_order_amount, max_discount_amount) VALUES (?, ?, ?, ?, ?)",
                (discount.name, discount.type, discount.value, discount.min_order_amount, discount.max_discount_amount),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Discount]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM discounts WHERE id = ?", (id,)
            ).fetchone()
            return Discount(**dict(row)) if row else None

    def get_all(self) -> List[Discount]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM discounts ORDER BY id"
            ).fetchall()
            return [Discount(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, type: Optional[Any] = None, min_order_amount: Optional[Any] = None, max_discount_amount: Optional[Any] = None, value: Optional[Any] = None) -> List[Discount]:
        with self.db.connect() as conn:
            query = "SELECT * FROM discounts WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if type is not None:
                query += ' AND type = ?'
                params.append(type)
            if min_order_amount is not None:
                query += ' AND min_order_amount >= ?'
                params.append(min_order_amount)
            if max_discount_amount is not None:
                query += ' AND max_discount_amount <= ?'
                params.append(max_discount_amount)
            if value is not None:
                query += ' AND value = ?'
                params.append(value)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Discount(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'type', 'value', 'min_order_amount', 'max_discount_amount']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE discounts SET " + ", ".join("%s = ?" % k for k in sets) +
                " WHERE id = ?",
                list(data[k] for k in sets) + [id]
            )
            conn.commit()
            return cur.rowcount > 0
