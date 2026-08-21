"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict, List, Optional

from budget_repository import BudgetRepository
from category_repository import CategoryRepository
from database import Database
from expense_repository import ExpenseRepository


class ExpenseService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.budget_repo = BudgetRepository(db)
        self.category_repo = CategoryRepository(db)
        self.expense_repo = ExpenseRepository(db)

    def list_expenses(self, category_id: Optional[int] = None, start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None, payment_method: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.expense_repo.list(
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
            payment_method=payment_method,
        )

    def get_expense_by_id(self, id: int) -> Optional[Dict[str, Any]]:
        return self.expense_repo.get_by_id(id)

    def add_expense(self, expense_data: Dict[str, Any]) -> None:
        raise NotImplementedError()

    def update_expense(self, id: int, data: Dict[str, Any]) -> None:
        self.expense_repo.update(id, data)

    def delete_expense(self, id: int) -> None:
        self.expense_repo.delete(id)

    def get_monthly_report(self, month: str) -> Dict[str, Any]:
        expenses = self.expense_repo.list(
            start_date=month + '-01', end_date=month + '-31',
        )
        total = sum(e.amount_cents for e in expenses)
        return {'month': month, 'total_spent': total}

    def get_yearly_summary(self, year: int) -> Dict[str, Any]:
        expenses = self.expense_repo.list(
            start_date=str(year) + '-01-01',
            end_date=str(year) + '-12-31',
        )
        total = sum(e.amount_cents for e in expenses)
        return {'year': year, 'total_yearly': total}

    def get_category_spending(self, category_id: int, start_date: datetime.date, end_date: datetime.date) -> Dict[str, int]:
        expenses = self.expense_repo.list(
            category_id=category_id,
            start_date=start_date,
            end_date=end_date,
        )
        total = sum(e.amount_cents for e in expenses)
        return {'total_spent': total}

    def export_to_csv(self, file_path: str, start_date: datetime.date, end_date: datetime.date) -> None:
        expenses = self.expense_repo.list(
            start_date=start_date, end_date=end_date,
        )
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'amount_cents', 'description', 'expense_date',
                'category_id', 'payment_method', 'is_recurring',
            ])
            for exp in expenses:
                writer.writerow([
                    exp.id, exp.amount_cents, exp.description, exp.expense_date,
                    exp.category_id, exp.payment_method, exp.is_recurring,
                ])

    def detect_recurring(self, start_date: datetime.date, end_date: datetime.date) -> List[Dict[str, Any]]:
        results = []
        groups = {}
        for exp in self.expense_repo.list():
            key = (exp.category_id, exp.description, exp.amount_cents)
            groups.setdefault(key, []).append(exp)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'category_id': key[0],
                    'description': key[1],
                    'amount_cents': key[2],
                    'count': len(group),
                })
        return results

