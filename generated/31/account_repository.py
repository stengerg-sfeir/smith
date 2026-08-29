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

    def list(self, customer_id: Optional[Any] = None, balance: Optional[Any] = None, created_at: Optional[Any] = None, max_balance: Optional[Any] = None) -> List[Account]:
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
            if max_balance is not None:
                query += ' AND balance <= ?'
                params.append(max_balance)
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
        return []

    def get_customer_accounts_summary(self, customer_id: int, min_balance: float, max_balance: float) -> list[dict[str, any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT r.* FROM accounts r JOIN customers o ON r.customer_id = o.id WHERE o.name = ? AND r.created_at >= ? AND r.created_at <= ?",
                (customer_id, min_balance, max_balance)
            ).fetchall()
            return [Account(**dict(r)) for r in rows]

    def get_total_balance_by_customer(self) -> dict[int, float]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT o.name AS k, SUM(e.balance) AS v FROM accounts e JOIN customers o ON e.customer_id = o.id GROUP BY o.name",
            ).fetchall()
            return {r["k"]: float(r["v"] or 0) for r in rows}

    def get_accounts_with_recent_activity(self, days_ago: int, threshold_amount: float) -> list[Account]:
        threshold_date = f"datetime('now', '-{days_ago} days')"
        query = '\n            SELECT DISTINCT a.id, a.balance, a.created_at, a.customer_id\n            FROM accounts a\n            JOIN deposits d ON a.id = d.account_id\n            WHERE d.created_at >= ? AND d.amount >= ?\n            UNION\n            SELECT DISTINCT a.id, a.balance, a.created_at, a.customer_id\n            FROM accounts a\n            JOIN withdrawals w ON a.id = w.account_id\n            WHERE w.created_at >= ? AND w.amount >= ?\n        '
        with self.db.connect() as conn:
            rows = conn.execute(query, (threshold_date, threshold_amount, threshold_date, threshold_amount)).fetchall()
        return [Account(**dict(r)) for r in rows]

    def get_account_balance_with_transaction_count(self, account_id: int) -> dict[str, any]:
        query = '\n            SELECT a.balance, \n                   (SELECT COUNT(*) FROM deposits WHERE account_id = ?) AS deposit_count,\n                   (SELECT COUNT(*) FROM withdrawals WHERE account_id = ?) AS withdrawal_count\n            FROM accounts a WHERE a.id = ?\n        '
        with self.db.connect() as conn:
            row = conn.execute(query, (account_id, account_id, account_id)).fetchone()
        if row is None:
            return {}
        return {'balance': row[0], 'deposit_count': row[1], 'withdrawal_count': row[2]}

    def get_total_deposits_and_withdrawals_by_account(self, account_id: int) -> dict[str, float]:
        query = "\n            SELECT \n                SUM(CASE WHEN t.type = 'deposit' THEN t.amount ELSE 0 END) AS total_deposits,\n                SUM(CASE WHEN t.type = 'withdrawal' THEN t.amount ELSE 0 END) AS total_withdrawals\n            FROM (\n                SELECT amount, 'deposit' AS type FROM deposits WHERE account_id = ?\n                UNION ALL\n                SELECT amount, 'withdrawal' AS type FROM withdrawals WHERE account_id = ?\n            ) AS t\n        "
        with self.db.connect() as conn:
            row = conn.execute(query, (account_id, account_id)).fetchone()
        return {'total_deposits': row[0] if row[0] is not None else 0.0, 'total_withdrawals': row[1] if row[1] is not None else 0.0}

