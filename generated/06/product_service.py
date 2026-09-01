"""Service layer."""
from __future__ import annotations

from typing import Optional

from database import Database
from exceptions import (
    DuplicateEntryError,
    InvalidPriceError,
    InvalidQuantityError,
    ValidationError,
)
from models import Product
from product_repository import ProductRepository


class ProductService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.product_repo = ProductRepository(db)

    def add_product(self, name: str, description: str, price: str, quantity: int) -> bool:
        product = Product(name=name, description=description, price=price, quantity=quantity)
        return self.product_repo.create(product)

    def list_product(self, name: Optional[str] = None, price: Optional[str] = None, price_max: Optional[str] = None, quantity: Optional[str] = None, quantity_max: Optional[str] = None) -> list[Product]:
        return self.product_repo.list(name=name, price=price, price_max=price_max, quantity=quantity, quantity_max=quantity_max)

    def update_product(self, id: int, name: Optional[str] = None, description: Optional[str] = None, price: Optional[str] = None, quantity: Optional[int] = None) -> bool:
        data = {k: v for k, v in {'name': name, 'description': description, 'price': price, 'quantity': quantity}.items() if v is not None}
        return self.product_repo.update(id, data)

    def delete_product(self, id: int) -> bool:
        return self.product_repo.delete(id)

    def persist_product(self, id: int) -> bool:
        try:
            existing_product = self.product_repo.get_by_id(id)
            if existing_product:
                product_data = {'name': existing_product.name, 'price': existing_product.price, 'quantity': existing_product.quantity, 'description': existing_product.description}
                self.product_repo.update(id, product_data)
                return True
            else:
                new_product = Product(description='', id=id, name='', price=0.0, quantity=0)
                self.product_repo.create(new_product)
                return True
        except (DuplicateEntryError, InvalidPriceError, InvalidQuantityError, ValidationError) as e:
            raise e
        except Exception as e:
            raise RuntimeError(f'Unexpected error during product persistence: {str(e)}')

