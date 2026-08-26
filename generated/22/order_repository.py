"""OrderRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import Order, OrderItem, Product


class OrderRepository:
    """SQLite repository for Order over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order: Order) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orders (customer_name, created_at, updated_at) VALUES (?, ?, ?)",
                (order.customer_name, order.created_at, order.updated_at),
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

    def list(self, customer_name: Optional[Any] = None, created_at: Optional[Any] = None) -> List[Order]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orders WHERE 1=1"
            params: List[Any] = []
            if customer_name is not None:
                query += ' AND customer_name = ?'
                params.append(customer_name)
            if created_at is not None:
                query += ' AND created_at >= ?'
                params.append(created_at)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Order(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_name', 'created_at', 'updated_at']
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

    def get_order_with_items_by_customer(self, customer_name: str) -> list[OrderWithItems]:
        return self.list(
            customer_name=customer_name,
        )

    def get_total_orders_by_customer(self, customer_name: str) -> int:
        return self.list(
            customer_name=customer_name,
        )

    def get_order_total_by_customer(self, customer_name: str) -> float:
        return self.list(
            customer_name=customer_name,
        )

    def get_product_usage_in_orders(self, product_name: str) -> dict[str, int]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT products.name, SUM(orderitems.quantity) AS total_quantity FROM products JOIN orderitems ON products.id = orderitems.product_id WHERE products.name = ?', (product_name,)).fetchall()
            result = {}
            for r in rows:
                result[r['name']] = r['total_quantity']
            return result

    def get_orders_with_high_value_items(self, min_total_amount: float) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE (SELECT SUM(orderitems.quantity * orderitems.unit_price) FROM orderitems WHERE orderitems.order_id = orders.id) >= ?', (min_total_amount,)).fetchall()
            return [Order(**dict(r)) for r in rows]

    def get_order_items_by_product_name(self, product_name: str, min_quantity: int) -> list[OrderItem]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orderitems JOIN products ON orderitems.product_id = products.id WHERE products.name = ? AND orderitems.quantity >= ?', (product_name, min_quantity)).fetchall()
            return [OrderItem(**dict(r)) for r in rows]

    def get_order_summary_by_date_range(self, start_date: str, end_date: str) -> dict[str, float]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT substr(orders.created_at, 1, 7) AS month, SUM(orderitems.quantity * orderitems.unit_price) AS total_revenue FROM orders JOIN orderitems ON orders.id = orderitems.order_id WHERE orders.created_at BETWEEN ? AND ? GROUP BY substr(orders.created_at, 1, 7)', (start_date, end_date)).fetchall()
            result = {}
            for r in rows:
                result[r['month']] = r['total_revenue']
            return result

    def get_most_popular_product(self) -> Product:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT products.name, products.price FROM products JOIN orderitems ON products.id = orderitems.product_id GROUP BY products.id ORDER BY SUM(orderitems.quantity) DESC LIMIT 1').fetchall()
            if not rows:
                return Product(name='', price=0.0)
            row = rows[0]
            return Product(name=row['name'], price=row['price'])

    def get_orders_with_missing_products(self) -> list[Order]:
        with self.db.connect() as conn:
            rows = conn.execute('SELECT * FROM orders WHERE NOT EXISTS (SELECT 1 FROM orderitems WHERE orderitems.order_id = orders.id)').fetchall()
            return [Order(**dict(r)) for r in rows]

