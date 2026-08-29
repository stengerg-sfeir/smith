"""Service layer."""
from __future__ import annotations

from typing import Dict, List, Optional

from database import Database
from exceptions import (
    InvalidInputException,
    SortingException,
    ValidationException,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def list_products_by_name(self, sort_order: str, filter_name: Optional[str]=None) -> List[Product]:
        """
            List products filtered by name and sorted by name.
            """
        if sort_order not in ['asc', 'desc']:
            raise SortingException(f"Invalid sort order: {sort_order}. Must be 'asc' or 'desc'.")
        if filter_name is not None:
            filtered_products = self.product_repo.list_products_by_name(sort_order, filter_name)
        else:
            filtered_products = self.product_repo.list_products_by_name(sort_order, '')
        return filtered_products

    def list_products_by_price(self, sort_order: str, min_price: float, max_price: float) -> List[Product]:
        """
            List products within a price range and sorted by price.
            """
        if sort_order not in ['asc', 'desc']:
            raise SortingException(f"Invalid sort order: {sort_order}. Must be 'asc' or 'desc'.")
        if min_price < 0 or max_price < 0:
            raise ValidationException('Price values must be non-negative.')
        if min_price > max_price:
            raise InvalidInputException('Min price cannot be greater than max price.')
        products = self.product_repo.list_products_by_price(sort_order, min_price, max_price)
        return products

    def list_products_by_quantity(self, sort_order: str, min_quantity: int, max_quantity: int) -> List[Product]:
        """
            List products within a quantity range and sorted by quantity.
            """
        if sort_order not in ['asc', 'desc']:
            raise SortingException(f"Invalid sort order: {sort_order}. Must be 'asc' or 'desc'.")
        if min_quantity < 0 or max_quantity < 0:
            raise ValidationException('Quantity values must be non-negative.')
        if min_quantity > max_quantity:
            raise InvalidInputException('Min quantity cannot be greater than max quantity.')
        products = self.product_repo.list_products_by_quantity(sort_order, min_quantity, max_quantity)
        return products

    def get_product_count(self) -> int:
        """
            Get the total count of products in the repository.
            """
        return self.product_repo.get_product_count()

    def get_product_report_by_category(self, category: str) -> Dict[str, float]:
        """
            Get a report of total price by category.
            """
        if not category:
            raise InvalidInputException('Category must be provided.')
        report = self.product_repo.get_product_report_by_category(category)
        return report

    def list_products_with_pagination(self, page: int, page_size: int, sort_field: str, sort_order: str) -> List[Product]:
        """
            List products with pagination and sorting.
            """
        if page < 1:
            raise InvalidInputException('Page number must be at least 1.')
        if page_size <= 0:
            raise InvalidInputException('Page size must be positive.')
        if sort_order not in ['asc', 'desc']:
            raise SortingException(f"Invalid sort order: {sort_order}. Must be 'asc' or 'desc'.")
        valid_sort_fields = ['name', 'price', 'quantity']
        if sort_field not in valid_sort_fields:
            raise SortingException(f'Invalid sort field: {sort_field}. Must be one of {valid_sort_fields}.')
        products = self.product_repo.list_products_with_pagination(page=page, page_size=page_size, sort_field=sort_field, sort_order=sort_order)
        return products

