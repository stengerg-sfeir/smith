"""Service layer."""
from __future__ import annotations

from typing import Dict, List

from database import Database
from exceptions import NotFoundError, ValidationException
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def search_product(self, term: str) -> List[Product]:
        """Search products by name containing the given term."""
        if not term or not term.strip():
            raise ValidationException('Search term cannot be empty.')
        return self.product_repo.search_products_by_name(term)

    def filter_product(self, id: int) -> List[Product]:
        """Filter product by ID."""
        if id is None or id <= 0:
            raise ValidationException('Product ID must be a positive integer.')
        product = self.product_repo.get_by_id(id)
        if not product:
            raise NotFoundError(f'Product with ID {id} not found.')
        return [product]

    def specify_product(self, id: int) -> Dict:
        """Return product summary data for a given product ID."""
        if id is None or id <= 0:
            raise ValidationException('Product ID must be a positive integer.')
        product = self.product_repo.get_by_id(id)
        if not product:
            raise NotFoundError(f'Product with ID {id} not found.')
        summary = self.product_repo.get_product_summary()
        return {'average_price': summary.get('average_price'), 'total_products': summary.get('total_products'), 'total_value': summary.get('total_value')}

