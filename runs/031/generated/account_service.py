"""Service layer."""
from __future__ import annotations

import csv
import datetime

from account_repository import AccountRepository
from customer_repository import CustomerRepository
from database import Database
from exceptions import InsufficientFundsError, NotFoundError
from models import Account, Deposit, Withdrawal


class AccountService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.account_repo = AccountRepository(db)
        self.customer_repo = CustomerRepository(db)

    def create_deposit(self, account_id: int, amount: float) -> bool:
        deposit = Deposit(account_id=account_id, amount=amount, created_at=datetime.datetime.now().isoformat())
        return self.deposit_repo.create(deposit)

    def process_withdrawal(self, account_id: int, amount: float) -> bool:
        try:
            account = self.account_repo.get_by_id(account_id)
            if not account:
                raise NotFoundError(f'Account with id {account_id} not found')
            current_balance = account.balance
            if current_balance < amount:
                raise InsufficientFundsError(f'Insufficient funds for withdrawal of {amount}. Current balance: {current_balance}')
            new_balance = current_balance - amount
            account.balance = new_balance
            self.account_repo.update(account_id, {'balance': new_balance})
            withdrawal = Withdrawal(account_id=account_id, amount=amount, created_at=datetime.datetime.now(), id=None)
            self.account_repo.create(withdrawal)
            return True
        except Exception as e:
            raise e

    def get_account_balance_with_transaction_count(self, account_id: int) -> dict[str, any]:
        return self.account_repo.get_account_balance_with_transaction_count(account_id)

    def get_accounts_with_recent_activity(self, days_ago: int, threshold_amount: float) -> list[Account]:
        return self.account_repo.get_accounts_with_recent_activity(days_ago=days_ago, threshold_amount=threshold_amount)

    def export_account_transactions_to_csv(self, account_id: int, file_path: str) -> None:
        rows = self.account_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'customer_id', 'balance', 'created_at',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.customer_id, row.balance, row.created_at,
                ])

    def get_total_deposits_and_withdrawals_by_account(self, account_id: int) -> dict[str, float]:
        return self.account_repo.get_total_deposits_and_withdrawals_by_account(account_id)

    def get_customer_accounts_summary(self, customer_id: int, min_balance: float, max_balance: float) -> list[dict[str, any]]:
        rows = self.account_repo.list(customer_id=customer_id, max_balance=max_balance)
        total = sum(e.balance for e in rows)
        return {'total_balance_filtered': total}

