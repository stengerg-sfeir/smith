"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from budget_repository import BudgetRepository
from category_repository import CategoryRepository
from database import Database
from exceptions import (
    BudgetExceededException,
    CategoryNotFoundError,
)
from expense_repository import ExpenseRepository
from models import Expense


class ExpenseService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.budget_repo = BudgetRepository(db)
        self.category_repo = CategoryRepository(db)
        self.expense_repo = ExpenseRepository(db)

    def list_expenses(self, category_id: Optional[int] = None, start_date: Optional[date] = None, end_date: Optional[date] = None, payment_method: Optional[str] = None) -> List[Expense]:
        return self.expense_repo.list(category_id=category_id, start_date=start_date, end_date=end_date, payment_method=payment_method)

    def get_expense_by_id(self, id: int) -> Optional[Expense]:
        return self.expense_repo.get_by_id(id)

    def add_expense(self, data: Dict[str, Any]) -> None:
        """
            Adds a new expense to the system.
        
            Args:
                data: Dictionary containing expense details including category_id, amount, description, 
                      date, and recurring (optional).
            """
        category_id = data.get('category_id')
        amount = data.get('amount_cents', data.get('amount'))
        description = data.get('description', '')
        date = data.get('expense_date', data.get('date'))
        recurring = data.get('is_recurring', data.get('recurring', False))
        if not category_id or not amount or (not date):
            raise ValueError('Category ID, amount, and date are required fields.')
        if self.category_repo.get_by_id(category_id) is None:
            raise CategoryNotFoundError(f'Category with ID {category_id} not found.')
        month = str(date)[:7]
        if self.check_budget_exceeded(category_id, month):
            raise BudgetExceededException(f'Expense exceeds the budget for category {category_id} in month {month}.')
        expense = Expense(
            amount_cents=amount,
            description=description,
            expense_date=date,
            category_id=category_id,
            payment_method=data.get('payment_method', 'card'),
            is_recurring=bool(recurring),
        )
        return self.expense_repo.create(expense)

    def update_expense(self, id: int, data: Dict[str, Any]) -> None:
        self.expense_repo.update(id, data)

    def delete_expense(self, id: int) -> None:
        return self.expense_repo.delete(id)

    def get_monthly_report(self, month: str) -> Dict[str, Any]:
        rows = [
            e for e in self.expense_repo.list()
            if str(e.expense_date)[:7] == month
        ]
        total = sum(e.amount_cents for e in rows)
        breakdown = {}
        for e in rows:
            breakdown[e.category_id] = breakdown.get(e.category_id, 0) + e.amount_cents
        return {'month': month, 'total_spent': total, 'by_category': breakdown}

    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
        rows = self.expense_repo.list(
            start_date=str(year) + '-01-01',
            end_date=str(year) + '-12-31',
        )
        total = sum(e.amount_cents for e in rows)
        return {'year': year, 'total_yearly_spent': total}

    def get_category_spending(self, category_id: int, start_date: date, end_date: date) -> int:
        rows = self.expense_repo.list(
            category_id=category_id,
            start_date=str(start_date),
            end_date=str(end_date),
        )
        return sum(e.amount_cents for e in rows)

    def export_to_csv(self, file_path: str, start_date: date, end_date: date) -> None:
        rows = self.expense_repo.list(start_date=start_date, end_date=end_date, )
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'amount_cents', 'description', 'expense_date',
                'category_id', 'payment_method', 'is_recurring',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.amount_cents, row.description, row.expense_date,
                    row.category_id, row.payment_method, row.is_recurring,
                ])

    def detect_recurring(self) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for row in self.expense_repo.list():
            key = (row.amount_cents, row.category_id)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'amount_cents': key[0],
                    'category_id': key[1],
                    'count': len(group),
                })
        return results

    def check_budget_exceeded(self, category_id: int, month: str) -> bool:
        """
            Checks if the expense for a given category and month exceeds the budget.
        
            Args:
                category_id: ID of the category to check.
                month: Month in format 'YYYY-MM' or 'YYYY-MM-DD'.
        
            Returns:
                True if the expense exceeds the budget, False otherwise.
            """
        budget_status = self.budget_repo.get_budget_status_for_category_month(category_id, month)
        if not budget_status:
            return False
        if isinstance(budget_status, dict):
            return (
                budget_status.get('total_spent', 0)
                > budget_status.get('total_budget', 0)
            )
        return budget_status.spending > budget_status.budget
