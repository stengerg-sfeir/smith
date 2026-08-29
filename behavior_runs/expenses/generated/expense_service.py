"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from budget_repository import BudgetRepository
from category_repository import CategoryRepository
from database import Database
from exceptions import (
    CategoryNotFoundError,
)
from expense_repository import ExpenseRepository
from models import Budget, Category, Expense


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
        if data.get('category_id') is not None:
            if self.category_repo.get_by_id(data.get('category_id')) is None:
                raise CategoryNotFoundError(data.get('category_id'))
        expense = Expense(**{k: v for k, v in data.items() if k in {'amount_cents', 'category_id', 'description', 'expense_date', 'id', 'is_recurring', 'payment_method'}})
        return self.expense_repo.create(expense)

    def update_expense(self, id: int, data: Dict[str, Any]) -> None:
        self.expense_repo.update(id, data)

    def delete_expense(self, id: int) -> None:
        return self.expense_repo.delete(id)

    def get_monthly_report(self, month: str) -> Dict[str, Any]:
        results = {}
        for row in self.expense_repo.list():
            key = row.category_id
            results[key] = results.get(key, 0) + row.amount_cents
        return results

    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
        rows = self.expense_repo.list(
            start_date=str(year) + '-01-01',
            end_date=str(year) + '-12-31',
        )
        total = sum(e.amount_cents for e in rows)
        return {'year': year, 'total_yearly_spent': total}

    def get_category_spending(self, category_id: int, start_date: date, end_date: date) -> int:
        return self.expense_repo.get_category_spending_range(category_id, start_date, end_date)

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
        return self.expense_repo.check_budget_exceeded(category_id, month)

    def add_category(self, name: str, description: str, monthly_budget: int, icon: str) -> int:
        category = Category(name=name, description=description, monthly_budget=monthly_budget, icon=icon)
        return self.category_repo.create(category)

    def list_category(self) -> List[Category]:
        return self.category_repo.list()

    def update_category(self, id: int, name: str, description: str, monthly_budget: int, icon: str) -> bool:
        data = {k: v for k, v in {'name': name, 'description': description, 'monthly_budget': monthly_budget, 'icon': icon}.items() if v is not None}
        return self.category_repo.update(id, data)

    def delete_category(self, id: int) -> bool:
        return self.category_repo.delete(id)

    def list_budget(self, category_id: int, month: str) -> List[Budget]:
        return self.budget_repo.list(category_id=category_id, month=month)

    def add_budget(self, category_id: int, month: str, amount_limit_cents: int) -> int:
        if category_id is not None:
            if self.category_repo.get_by_id(category_id) is None:
                raise CategoryNotFoundError(category_id)
        budget = Budget(category_id=category_id, month=month, amount_limit_cents=amount_limit_cents)
        return self.budget_repo.create(budget)

    def update_budget(self, category_id: int, month: str, amount_limit_cents: int) -> bool:
        row = self.budget_repo.get_by_category_and_month(category_id, month)
        if row is None:
            return False
        data = {k: v for k, v in {'amount_limit_cents': amount_limit_cents}.items() if v is not None}
        return self.budget_repo.update(row.id, data)

    def delete_budget(self, category_id: int, month: str) -> bool:
        return self.budget_repo.delete(category_id, month)

