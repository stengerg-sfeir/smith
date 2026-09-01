"""SaleRepository data access."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database import Database
from exceptions import SaleNotFoundError
from models import Product, Sale


class SaleRepository:
    """SQLite repository for Sale over the shared Database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def create(self, sale: Sale) -> int:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO sales (customer_id, product_id, quantity, total_price, sale_date) VALUES (?, ?, ?, ?, ?)",
                (sale.customer_id, sale.product_id, sale.quantity, sale.total_price, sale.sale_date),
            )
            conn.commit()
            return cur.lastrowid

    def get_by_id(self, id: int) -> Optional[Sale]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sales WHERE id = ?", (id,)
            ).fetchone()
            return Sale(**dict(row)) if row else None

    def get_all(self) -> List[Sale]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sales ORDER BY id"
            ).fetchall()
            return [Sale(**dict(r)) for r in rows]

    def list(self, customer_id: Optional[Any] = None, product_id: Optional[Any] = None, start_date: Optional[Any] = None, end_date: Optional[Any] = None, start_month: Optional[Any] = None, end_month: Optional[Any] = None, start_year: Optional[Any] = None, end_year: Optional[Any] = None) -> List[Sale]:
        with self.db.connect() as conn:
            query = "SELECT * FROM sales WHERE 1=1"
            params: List[Any] = []
            if customer_id is not None:
                query += ' AND customer_id = ?'
                params.append(customer_id)
            if product_id is not None:
                query += ' AND product_id = ?'
                params.append(product_id)
            if start_date is not None:
                query += ' AND sale_date >= ?'
                params.append(start_date)
            if end_date is not None:
                query += ' AND sale_date <= ?'
                params.append(end_date)
            if start_month is not None:
                query += ' AND sale_date >= ?'
                params.append(start_month)
            if end_month is not None:
                query += ' AND sale_date <= ?'
                params.append(end_month)
            if start_year is not None:
                query += ' AND sale_date >= ?'
                params.append(start_year)
            if end_year is not None:
                query += ' AND sale_date <= ?'
                params.append(end_year)
            rows = conn.execute(query + " ORDER BY id", params).fetchall()
            return [Sale(**dict(r)) for r in rows]

    def update(self, id: int, data: Dict[str, Any]) -> bool:
        if not data:
            return False
        allowed = ['customer_id', 'product_id', 'quantity', 'total_price', 'sale_date']
        sets = [k for k in data if k in allowed]
        if not sets:
            return False
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE sales SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",
                [data[k] for k in sets] + [id],
            )
            conn.commit()
            if cur.rowcount == 0:
                raise SaleNotFoundError(id)
            return True

    def delete(self, id: int) -> bool:
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "DELETE FROM sales WHERE id = ?", (id,)
            )
            conn.commit()
            return cur.rowcount > 0

    def get_sales_by_date_range(self, start_date: datetime, end_date: datetime) -> list[Sale]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

    def get_sales_by_product(self, product_id: int, start_date: datetime, end_date: datetime) -> list[Sale]:
        return self.list(
            product_id=product_id,
            start_date=start_date,
            end_date=end_date,
        )

    def get_sales_by_customer(self, customer_id: int, start_date: datetime, end_date: datetime) -> list[Sale]:
        return self.list(
            customer_id=customer_id,
            start_date=start_date,
            end_date=end_date,
        )

    def get_total_revenue_by_date_range(self, start_date: datetime, end_date: datetime) -> float:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(total_price), 0) AS v FROM sales WHERE sale_date >= ? AND sale_date <= ?",
                (start_date, end_date)
            ).fetchone()
            return float(row["v"])

    def get_total_sales_count_by_date_range(self, start_date: datetime, end_date: datetime) -> int:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) AS v FROM sales WHERE sale_date >= ? AND sale_date <= ?",
                (start_date, end_date)
            ).fetchone()
            return int(row["v"])

    def get_top_selling_products_by_date_range(self, start_date: str, end_date: str, limit: int) -> list[Product]:
        with self.db.connect() as conn:
            query = '\n                SELECT p.id, p.name, p.price, p.stock_quantity, p.updated_at\n                FROM sales s\n                JOIN products p ON s.product_id = p.id\n                WHERE s.sale_date BETWEEN ? AND ?\n                ORDER BY s.quantity DESC\n                LIMIT ?\n            '
            rows = conn.execute(query, (start_date, end_date, limit)).fetchall()
            return [Product(**dict(r)) for r in rows]

    def get_sales_summary_by_month(self, start_year: int, start_month: int, end_year: int, end_month: int) -> dict[str, float]:
        with self.db.connect() as conn:
            query = '\n                SELECT \n                    substr(s.sale_date, 1, 7) AS month,\n                    SUM(s.total_price) AS total_revenue\n                FROM sales s\n                WHERE s.sale_date >= ? \n                  AND s.sale_date < ?\n                GROUP BY substr(s.sale_date, 1, 7)\n                ORDER BY substr(s.sale_date, 1, 7)\n            '
            start_date = f'{start_year}-{str(start_month).zfill(2)}-01'
            end_date = f'{end_year}-{str(end_month).zfill(2)}-01'
            if end_month == 12:
                end_date = f'{end_year + 1}-01-01'
            else:
                end_date = f'{end_year}-{str(end_month + 1).zfill(2)}-01'
            rows = conn.execute(query, (start_date, end_date)).fetchall()
            result = {}
            for row in rows:
                month = row[0]
                revenue = row[1]
                result[month] = revenue
            return result

    def get_sales_with_product_details(self, start_date: datetime, end_date: datetime) -> list[dict[str, any]]:
        return self.list(
            start_date=start_date,
            end_date=end_date,
        )

