"""OrderItemRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from models import OrderItem


class OrderItemRepository:
    """SQLite repository for OrderItem over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, order_item: OrderItem) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO orderitems (order_id, product_id, quantity, unit_price, created_at) VALUES (?, ?, ?, ?, ?)",
                (order_item.order_id, order_item.product_id, order_item.quantity, order_item.unit_price, order_item.created_at),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[OrderItem]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM orderitems WHERE id = ?", (id,)
            ).fetchone()
            return OrderItem(**dict(row)) if row else None

    def get_all(self) -> List[OrderItem]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM orderitems ORDER BY id"
            ).fetchall()
            return [OrderItem(**dict(r)) for r in rows]

    def list(self, order_id: Optional[Any] = None, product_id: Optional[Any] = None, quantity: Optional[Any] = None, unit_price: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> List[OrderItem]:
        with self.db.connect() as conn:
            query = "SELECT * FROM orderitems WHERE 1=1"
            params: List[Any] = []
            if order_id is not None:
                query += ' AND order_id = ?'
                params.append(order_id)
            if product_id is not None:
                query += ' AND product_id = ?'
                params.append(product_id)
            if quantity is not None:
                query += ' AND quantity >= ?'
                params.append(quantity)
            if unit_price is not None:
                query += ' AND unit_price >= ?'
                params.append(unit_price)
            if start_date is not None:
                query += ' AND created_at >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND created_at <= ?'
                params.append(end_date)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [OrderItem(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['order_id', 'product_id', 'quantity', 'unit_price', 'created_at']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE orderitems SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
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
                "DELETE FROM orderitems WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_order_items_by_quantity_range(self, min_quantity: int, max_quantity: int) -> list[OrderItem]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM orderitems WHERE quantity BETWEEN ? AND ?', (min_quantity, max_quantity))
            rows = cursor.fetchall()
            return [OrderItem(**dict(r)) for r in rows]

    def get_order_items_by_product_and_date_range(self, product_name: str, start_date: datetime, end_date: datetime) -> list[OrderItem]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_order_items_with_high_value_total(self, min_total_value: float) -> list[OrderItem]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM orderitems WHERE quantity * unit_price >= ?', (min_total_value,))
            rows = cursor.fetchall()
            return [OrderItem(**dict(r)) for r in rows]

    def get_order_items_by_order_date_and_product_category(self, start_date: datetime, end_date: datetime, product_category: str) -> list[OrderItem]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_total_quantity_sold_per_product(self) -> dict[str, int]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT product_id, SUM(quantity) AS total_quantity FROM orderitems GROUP BY product_id')
            rows = cursor.fetchall()
            result = {}
            for row in rows:
                product_id = row[0]
                total_quantity = row[1]
                result[str(product_id)] = total_quantity
            return result

    def get_order_items_with_missing_product_data(self) -> list[OrderItem]:
        with self.db.connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM orderitems WHERE product_id IS NULL OR product_id = ''")
            rows = cursor.fetchall()
            return [OrderItem(**dict(r)) for r in rows]

    def get_order_items_by_customer_and_date_range(self, customer_name: str, start_date: datetime, end_date: datetime) -> list[OrderItem]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

