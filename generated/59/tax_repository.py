"""TaxRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Tax


class TaxRepository:
    """SQLite repository for Tax over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, tax: Tax) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO taxs (name, rate, tax_type) VALUES (?, ?, ?)",
                (tax.name, tax.rate, tax.tax_type),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Tax]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM taxs WHERE id = ?", (id,)
            ).fetchone()
            return Tax(**dict(row)) if row else None

    def get_all(self) -> List[Tax]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM taxs ORDER BY id"
            ).fetchall()
            return [Tax(**dict(r)) for r in rows]

    def list(self, name: Optional[Any] = None, rate: Optional[Any] = None, tax_type: Optional[Any] = None, max_rate: Optional[Any] = None, min_rate: Optional[Any] = None) -> List[Tax]:
        with self.db.connect() as conn:
            query = "SELECT * FROM taxs WHERE 1=1"
            params: List[Any] = []
            if name is not None:
                query += ' AND name = ?'
                params.append(name)
            if rate is not None:
                query += ' AND rate = ?'
                params.append(rate)
            if tax_type is not None:
                query += ' AND tax_type = ?'
                params.append(tax_type)
            if max_rate is not None:
                query += ' AND rate <= ?'
                params.append(max_rate)
            if min_rate is not None:
                query += ' AND rate >= ?'
                params.append(min_rate)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Tax(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['name', 'rate', 'tax_type']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE taxs SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                return False
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM taxs WHERE id = ?", (id,))
            conn.commit()
            return cur.rowcount > 0
