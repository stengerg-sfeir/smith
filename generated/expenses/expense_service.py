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
    ExpenseNotFoundError,
)
from expense_repository import ExpenseRepository
from models import Budget, Category, Expense


class ExpenseService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.budget_repo = BudgetRepository(db)
        self.category_repo = CategoryRepository(db)
        self.expense_repo = ExpenseRepository(db)

    def add(self, amount_cents: int, description: str, category_id: int, expense_date: Optional[str]=None, payment_method: Optional[str]=None, is_recurring: bool=None) -> None:
        try:
            category = self.category_repo.get_by_id(category_id)
            if not category:
                raise CategoryNotFoundError(f'Category with id {category_id} not found')
        except CategoryNotFoundError:
            raise CategoryNotFoundError(f'Category with id {category_id} not found')
        expense = Expense(amount_cents=amount_cents, category_id=category_id, description=description, expense_date=expense_date, is_recurring=is_recurring, payment_method=payment_method)
        month = expense.expense_date.split('-')[1] if expense_date else None
        if month:
            month = month.zfill(2)
            budget_exceeded = self.expense_repo.check_budget_exceeded(category_id, month)
            if budget_exceeded:
                raise BudgetExceededException(f'Expense exceeds the monthly budget for category {category_id}')
        self.expense_repo.create(expense)
        category_budget_status = self.category_repo.get_category_budget_status(category_id, month)
        if category_budget_status:
            if category_budget_status['usage_percentage'] >= 100:
                raise BudgetExceededException(f'Category {category_id} budget exceeded')

    def list(self, category_id: Optional[int]=None, from_date: Optional[str]=None, to_date: Optional[str]=None, payment_method: Optional[str]=None) -> List[Expense]:
        filters = {}
        if category_id is not None:
            filters['category_id'] = category_id
        if from_date is not None:
            filters['from_date'] = from_date
        if to_date is not None:
            filters['to_date'] = to_date
        if payment_method is not None:
            filters['payment_method'] = payment_method
        expenses = self.expense_repo.list(**filters)
        return expenses

    def update(self, id: int, name: Optional[str]=None, description: Optional[str]=None, budget: Optional[str]=None, icon: Optional[str]=None) -> None:
        try:
            expense = self.expense_repo.get_by_id(id)
            if not expense:
                raise ExpenseNotFoundError(f'Expense with id {id} not found')
        except ExpenseNotFoundError:
            raise ExpenseNotFoundError(f'Expense with id {id} not found')
        update_data = {}
        if description is not None:
            update_data['description'] = description
        if name is not None:
            update_data['name'] = name
        if budget is not None:
            try:
                budget_cents = int(budget)
                update_data['budget'] = budget_cents
            except ValueError:
                raise ValueError('Invalid budget value')
        if icon is not None:
            update_data['icon'] = icon
        self.expense_repo.update(id, update_data)
        if 'budget' in update_data:
            category_id = expense.category_id
            month = expense.expense_date.split('-')[1] if expense.expense_date else None
            if month:
                month = month.zfill(2)
                budget_exceeded = self.expense_repo.check_budget_exceeded(category_id, month)
                if budget_exceeded:
                    raise BudgetExceededException(f'Expense exceeds the monthly budget for category {category_id}')

    def delete(self, id: int) -> None:
        try:
            expense = self.expense_repo.get_by_id(id)
            if not expense:
                raise ExpenseNotFoundError(f'Expense with id {id} not found')
        except ExpenseNotFoundError:
            raise ExpenseNotFoundError(f'Expense with id {id} not found')
        self.expense_repo.delete(id)

    def add_category(self, name: str, description: str, budget: Optional[str] = None, icon: Optional[str] = None) -> None:
        category = Category(name=name, description=description, icon=icon)
        return self.category_repo.create(category)

    def list_category(self) -> List[Category]:
        return self.category_repo.list()

    def update_category(self, id: int, name: Optional[str] = None, description: Optional[str] = None, budget: Optional[str] = None, icon: Optional[str] = None) -> None:
        data = {k: v for k, v in {'name': name, 'description': description, 'icon': icon}.items() if v is not None}
        return self.category_repo.update(id, data)

    def delete_category(self, id: int) -> None:
        return self.category_repo.delete(id)

    def list_budget(self, category_id: Optional[int] = None, month: Optional[str] = None) -> List[Budget]:
        return self.budget_repo.list(category_id=category_id, month=month)

    def add_budget(self, category_id: int, month: str, amount_limit_cents: int) -> None:
        if category_id is not None:
            if self.category_repo.get_by_id(category_id) is None:
                raise CategoryNotFoundError(category_id)
        budget = Budget(category_id=category_id, month=month, amount_limit_cents=amount_limit_cents)
        return self.budget_repo.create(budget)

    def update_budget(self, category_id: int, month: str, amount_limit_cents: Optional[int] = None) -> None:
        row = self.budget_repo.get_by_category_and_month(category_id, month)
        if row is None:
            return False
        data = {k: v for k, v in {'amount_limit_cents': amount_limit_cents}.items() if v is not None}
        return self.budget_repo.update(row.id, data)

    def delete_budget(self, category_id: int, month: str) -> None:
        return self.budget_repo.delete(category_id, month)

    def report(self, month: str) -> Dict[str, Any]:
        rows = self.expense_repo.list(
            start_date=month + '-01',
            end_date=month + '-31',
        )
        total = sum(e.amount_cents for e in rows)
        return {'month': month, 'total_spent': total}

    def export(self, from_date: str, to_date: str, output: str) -> None:
        rows = self.expense_repo.list()
        with open(output, "w", newline="", encoding="utf-8") as f:
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
        results = {}
        for row in self.expense_repo.list():
            key = (row.category_id, row.amount_cents)
            results[key] = results.get(key, 0) + row.amount_cents
        return results

