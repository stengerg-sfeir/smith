"""AccountRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Account, Deposit, Withdrawal


class AccountRepository:
    """SQLite repository for Account over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, account: Account) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO accounts (customer_id, balance, created_at) VALUES (?, ?, ?)",
                (account.customer_id, account.balance, account.created_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Account]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ?", (id,)
            ).fetchone()
            return Account(**dict(row)) if row else None

    def get_all(self) -> List[Account]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM accounts ORDER BY id"
            ).fetchall()
            return [Account(**dict(r)) for r in rows]

    def list(self, customer_id: Optional[Any] = None, balance: Optional[Any] = None, created_at: Optional[Any] = None) -> List[Account]:
        with self.db.connect() as conn:
            query = "SELECT * FROM accounts WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if balance is not None:
                query += ' AND balance >= ?'
                params.append(balance)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Account(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'balance', 'created_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE accounts SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM accounts WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_account_with_history(self, account_id: int, include_deposits: bool, include_withdrawals: bool) -> Optional[Union[list[Deposit, Withdrawal]]]:
        raise NotImplementedError()

    def get_customer_accounts_summary(self, customer_id: int, min_balance: float, max_balance: float) -> list[dict[str, any]]:
        return self.list(
            customer_id=customer_id,
        )

    def get_total_balance_by_customer(self) -> dict[int, float]:
        raise NotImplementedError()

    def get_accounts_with_recent_activity(self, days_ago: int, threshold_amount: float) -> list[Account]:
        raise NotImplementedError()

    def get_account_balance_with_transaction_count(self, account_id: int) -> dict[str, any]:
        raise NotImplementedError()

    def get_total_deposits_and_withdrawals_by_account(self, account_id: int) -> dict[str, float]:
        raise NotImplementedError()

