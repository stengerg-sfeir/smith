"""UserRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Order, User


class UserRepository:
    """SQLite repository for User over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, user: User) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (email, password_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user.email, user.password_hash, user.role, user.created_at, user.updated_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[User]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (id,)
            ).fetchone()
            return User(**dict(row)) if row else None

    def get_all(self) -> List[User]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY id"
            ).fetchall()
            return [User(**dict(r)) for r in rows]

    def list(self, email: Optional[Any] = None, role: Optional[Any] = None, created_at: Optional[Any] = None, created_at_end: Optional[Any] = None, password_hash: Optional[Any] = None) -> List[User]:
        with self.db.connect() as conn:
            query = "SELECT * FROM users WHERE 1=1"
            params: List[Any] = []
            if email is not None:
                query += ' AND email = ?'
                params.append(email)
            if role is not None:
                query += ' AND role = ?'
                params.append(role)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            if created_at_end is not None:
                query += ' AND created_at <= ?'
                params.append(created_at_end)
            if password_hash is not None:
                query += ' AND password_hash = ?'
                params.append(password_hash)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [User(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['email', 'password_hash', 'role', 'created_at', 'updated_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE users SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM users WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_user_orders_by_status(self, user_id: int, status: str) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE user_id = ? AND status = ?', (user_id, status)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_product_sales_report(self, start_date: str, end_date: str) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT \n                    products.name AS product_name,\n                    SUM(orders.total_amount) AS total_sales,\n                    COUNT(orders.id) AS order_count\n                FROM orders\n                JOIN products ON orders.product_id = products.id\n                WHERE orders.created_at BETWEEN ? AND ?\n                GROUP BY products.name\n            ', (start_date, end_date)).fetchall()
            return {row['product_name']: {'total_sales': row['total_sales'], 'order_count': row['order_count']} for row in rows}

    def get_user_with_most_orders(self) -> User:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT \n                    users.id, \n                    users.email, \n                    users.role, \n                    users.created_at, \n                    users.updated_at\n                FROM users\n                JOIN orders ON users.id = orders.user_id\n                GROUP BY users.id\n                ORDER BY COUNT(orders.id) DESC\n                LIMIT 1\n            ').fetchone()
            if not rows:
                return User(id=None, email=None, password_hash=None, role=None, created_at=None, updated_at=None)
            return User(**dict(rows))

    def get_active_products_count(self) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM users",
            ).fetchone()
            return int(row["n"])

    def get_user_by_email_and_password(self, email: str, password_hash: str) -> User:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM users WHERE email = ? AND password_hash = ?', (email, password_hash)).fetchall()
            return [User(**dict(r)) for r in rows] if rows else []

    def get_user_orders_with_product_details(self, user_id: int) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute('\n                SELECT \n                    orders.id AS order_id,\n                    orders.status,\n                    orders.total_amount,\n                    orders.created_at,\n                    orders.updated_at,\n                    products.name AS product_name,\n                    products.price AS product_price,\n                    products.stock_quantity AS stock_quantity\n                FROM orders\n                JOIN products ON orders.product_id = products.id\n                WHERE orders.user_id = ?\n            ', (user_id,)).fetchall()
            return [dict(row) for row in rows]

    def get_total_orders_by_status(self, status: str) -> int:
        with self.db.connect() as conn:
            row = conn.execute('SELECT COUNT(*) FROM orders WHERE status = ?', (status,)).fetchone()
            return row[0] if row else 0

    def get_user_role_count(self) -> dict:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT role, COUNT(*) AS count FROM users GROUP BY role').fetchall()
            return {row['role']: row['count'] for row in rows}

