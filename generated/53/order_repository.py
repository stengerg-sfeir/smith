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
                "INSERT INTO orders (customer_id, created_at, updated_at) VALUES (?, ?, ?)",
                (order.customer_id, order.created_at, order.updated_at),
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

    def list(self, customer_id: Optional[Any] = None, created_at: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'created_at', 'updated_at']
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

    def create_order_with_validation(self, customer_id: int, order_items: list[dict[str, any]]) -> Order:
        with self.db.connect() as conn:
            for item in order_items:
                if 'product_id' not in item or 'quantity' not in item:
                    raise ValueError("Order item must have 'product_id' and 'quantity'")
            cursor = conn.execute('INSERT INTO orders (customer_id, created_at, updated_at) VALUES (?, ?, ?)', (customer_id, '2024-01-01', '2024-01-01'))
            order_id = cursor.lastrowid
            for item in order_items:
                product_id = item['product_id']
                quantity = item['quantity']
                conn.execute('INSERT INTO orderitems (order_id, product_id, quantity) VALUES (?, ?, ?)', (order_id, product_id, quantity))
            conn.commit()
            return Order(id=order_id, customer_id=customer_id)

    def get_order_by_id_with_items(self, order_id: int) -> OrderWithItems:
        return None

    def list_orders_by_customer(self, customer_id: int, start_date: datetime, end_date: datetime) -> list[Order]:
        return []

    def get_total_orders_by_customer(self, customer_id: int) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) FROM orders WHERE customer_id = ?', (customer_id,)).fetchone()
            return rows[0] if rows else 0

    def get_order_count_in_date_range(self, start_date: str, end_date: str) -> int:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT COUNT(*) FROM orders WHERE created_at BETWEEN ? AND ?', (start_date, end_date)).fetchone()
            return rows[0] if rows else 0

    def get_total_stock_value_in_order(self, order_id: int) -> float:
        with self.db.connect() as conn:
            items_rows = conn.execute('SELECT oi.product_id, oi.quantity FROM orderitems oi WHERE oi.order_id = ?', (order_id,)).fetchall()
            total_value = 0.0
            for row in items_rows:
                product_id = row[0]
                quantity = row[1]
                product_row = conn.execute('SELECT price FROM products WHERE id = ?', (product_id,)).fetchone()
                if product_row:
                    total_value += product_row[0] * quantity
            return total_value

    def list_orders_with_stock_status(self, min_stock_threshold: int, product_name_filter: str) -> list[OrderWithStockStatus]:
        return []

    def get_product_stock_summary(self) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT order_id AS k, COUNT(*) AS n FROM orderitems GROUP BY order_id ORDER BY n DESC"
            ).fetchall()
            return {r["k"]: int(r["n"]) for r in rows}

    def get_orders_with_low_stock_products(self) -> list[OrderWithLowStockProducts]:
        return []

