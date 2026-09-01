"""Service layer."""
from __future__ import annotations

from typing import Any, Dict, List

from customer_repository import CustomerRepository
from database import Database
from exceptions import (
    CustomerNotFoundError,
    InvalidCustomerIDError,
    PurchaseNotFoundError,
)
from purchase_repository import PurchaseRepository


class PurchaseService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.customer_repo = CustomerRepository(db)
        self.purchase_repo = PurchaseRepository(db)

    def search_customer(self, term: str) -> List[Dict[str, Any]]:
        """
            Search for customers by name or email containing the given term.
            Returns a list of dictionaries with customer details.
            """
        results = self.customer_repo.list(name__contains=term, email__contains=term)
        return [{'id': customer.id, 'name': customer.name, 'email': customer.email, 'phone': customer.phone} for customer in results]

    def get_customer_report(self, id: int) -> Dict[str, Any]:
        """
            Generate a comprehensive report for a customer including purchase history, total spending, and spending trends.
            """
        try:
            customer = self.customer_repo.get_by_id(id)
        except (CustomerNotFoundError, InvalidCustomerIDError) as e:
            raise CustomerNotFoundError(f'Customer with ID {id} not found.') from e
        try:
            purchase_history = self.purchase_repo.get_customer_purchase_history(customer_id=id, start_date=None, end_date=None)
        except Exception as e:
            raise PurchaseNotFoundError(f'Purchase history not available for customer ID {id}') from e
        total_spending = self.purchase_repo.get_customer_purchase_total(customer_id=id)
        spending_trend = self.purchase_repo.get_customer_spending_trend(customer_id=id, period='monthly')
        report = {'customer_id': id, 'name': customer.name, 'email': customer.email, 'phone': customer.phone, 'total_spending': total_spending, 'purchase_history': [{'id': purchase.id, 'amount': purchase.amount, 'purchase_date': purchase.purchase_date.isoformat() if purchase.purchase_date else None} for purchase in purchase_history], 'spending_trend': spending_trend}
        return report

