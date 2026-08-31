"""Service layer."""
from __future__ import annotations

import csv
import datetime

from account_repository import AccountRepository
from database import Database
from exceptions import NotFoundError
from models import Deposit, Withdrawal


class AccountService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.account_repo = AccountRepository(db)

    def create_deposit(self, account_id: int, amount: float) -> bool:
        deposit = Deposit(account_id=account_id, amount=amount, created_at=datetime.datetime.now().isoformat())
        return self.deposit_repo.create(deposit)

    def create_withdrawal(self, account_id: int, amount: float) -> bool:
        withdrawal = Withdrawal(account_id=account_id, amount=amount, created_at=datetime.datetime.now().isoformat())
        return self.withdrawal_repo.create(withdrawal)

    def get_account_balance_with_transaction_count(self, account_id: int) -> dict[str, any]:
        results = {}
        for row in self.deposit_repo.list(account_id=account_id):
            key = row.account_id
            results[key] = results.get(key, 0) + row.amount
        return results

    def get_customer_accounts_summary(self, customer_id: int, min_balance: float, max_balance: float) -> list[dict[str, any]]:
        results = []
        groups = {}
        for row in self.account_repo.list(customer_id=customer_id, max_balance=max_balance):
            key = (row.customer_id)
            groups.setdefault(key, []).append(row)
        for key, group in groups.items():
            if len(group) >= 2:
                results.append({
                    'customer_id': key[0],
                    'count': len(group),
                })
        return results

    def export_account_transactions_to_csv(self, account_id: int, file_path: str) -> None:
        rows = self.deposit_repo.list(account_id=account_id, )
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'account_id', 'amount', 'created_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.account_id, row.amount, row.created_at,
                ])

    def get_total_balance_by_customer(self) -> dict[int, float]:
        return self.account_repo.get_total_balance_by_customer()

    def find_accounts_with_negative_balance_after_withdrawal(self, account_id: int, withdrawal_amount: float) -> list[dict[str, any]]:
        account = self.account_repo.get_by_id(account_id)
        if not account:
            raise NotFoundError(f'Account with id {account_id} not found')
        balance_info = self.account_repo.get_account_balance_with_transaction_count(account_id)
        if not balance_info:
            raise NotFoundError(f'Account balance not found for account id {account_id}')
        current_balance = balance_info['balance']
        if current_balance - withdrawal_amount < 0:
            return [{'account_id': account_id, 'current_balance': current_balance, 'withdrawal_amount': withdrawal_amount, 'new_balance': current_balance - withdrawal_amount, 'would_be_negative': True}]
        else:
            return []

