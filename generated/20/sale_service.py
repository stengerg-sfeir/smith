"""Service layer."""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

from database import Database
from exceptions import SalesReportError
from models import Product, Sale
from product_repository import ProductRepository
from sale_repository import SaleRepository


class SaleService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)
        self.sale_repo = SaleRepository(db)

    def add_product(self, name: str, price: str) -> None:
        product = Product(name=name, price=price)
        return self.product_repo.create(product)

    def list_product(self) -> List[Dict[str, Any]]:
        return self.product_repo.list()

    def update_product(self, id: int, name: Optional[str] = None, price: Optional[str] = None) -> None:
        data = {k: v for k, v in {'name': name, 'price': price}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_product(self, id: int) -> None:
        return self.product_repo.delete(id)

    def add_sale(self, product_id: int, quantity: int) -> None:
        sale = Sale(product_id=product_id, quantity=quantity, sale_date=datetime.datetime.now().isoformat())
        return self.sale_repo.create(sale)

    def list_sale(self, product_id: Optional[str] = None, sale_date_from: Optional[str] = None, sale_date_to: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.sale_repo.list(product_id=product_id, sale_date_from=sale_date_from, sale_date_to=sale_date_to)

    def get_product_report(self, id: int) -> Dict[str, Any]:
        try:
            sales_report = self.sale_repo.get_sales_report_by_product(id)
            return sales_report
        except Exception as e:
            raise SalesReportError(f'Failed to generate product sales report: {str(e)}')

