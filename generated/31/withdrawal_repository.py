"""WithdrawalRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Withdrawal


class WithdrawalRepository:
    """SQLite repository for Withdrawal over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, withdrawal: Withdrawal) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO withdrawals (account_id, amount, created_at) VALUES (?, ?, ?)",
                (withdrawal.account_id, withdrawal.amount, withdrawal.created_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Withdrawal]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM withdrawals WHERE id = ?", (id,)
            ).fetchone()
            return Withdrawal(**dict(row)) if row else None

    def get_all(self) -> List[Withdrawal]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM withdrawals ORDER BY id"
            ).fetchall()
            return [Withdrawal(**dict(r)) for r in rows]

    def list(self, account_id: Optional[Any] = None, amount: Optional[Any] = None, created_at: Optional[Any] = None) -> List[Withdrawal]:
        with self.db.connect() as conn:
            query = "SELECT * FROM withdrawals WHERE 1=1"
            params: List[Any] = []
            if account_id is not None:
                query += ' AND account_id = ?'
                params.append(account_id)
            if amount is not None:
                query += ' AND amount >= ?'
                params.append(amount)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Withdrawal(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['account_id', 'amount', 'created_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE withdrawals SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM withdrawals WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

