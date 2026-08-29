"""Service layer."""
from __future__ import annotations

import csv
import datetime
from typing import Optional

from account_repository import AccountRepository
from customer_repository import CustomerRepository
from database import Database
from exceptions import InsufficientFundsError, NotFoundError
from models import Customer, Deposit, Withdrawal


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
            balance = account.balance
            if balance < amount:
                raise InsufficientFundsError(f'Insufficient funds for withdrawal of {amount}. Current balance: {balance}')
            new_balance = balance - amount
            self.account_repo.update(account_id, {'balance': new_balance})
            withdrawal = Withdrawal(account_id=account_id, amount=amount, created_at=datetime.datetime.now(), id=None)
            self.account_repo.create(withdrawal)
            return True
        except Exception as e:
            raise e

    def get_customer_with_most_total_transactions(self) -> Optional[Customer]:
        try:
            customer = self.customer_repo.get_customer_with_most_total_transactions()
            return customer
        except Exception as e:
            raise e

    def get_customers_with_active_accounts_and_balance_range(self, min_balance: float, max_balance: float) -> list[dict[str, any]]:
        try:
            customers = self.customer_repo.get_customers_with_active_accounts_and_balance_range(min_balance, max_balance)
            return customers
        except Exception as e:
            raise e

    def get_customers_with_recent_activity(self, days_ago: int, min_transaction_amount: float) -> list[Customer]:
        try:
            customers = self.customer_repo.get_customers_with_recent_activity(days_ago, min_transaction_amount)
            return customers
        except Exception as e:
            raise e

    def export_customer_transactions_to_csv(self, customer_id: int, file_path: str) -> None:
        rows = self.customer_repo.list()
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'name', 'email', 'phone',
            ])
            for row in rows:
                writer.writerow([
                    row.id, row.name, row.email, row.phone,
                ])

    def get_total_deposit_volume_by_customer(self) -> dict[int, float]:
        try:
            result = self.customer_repo.get_total_deposit_volume_by_customer()
            return result
        except Exception as e:
            raise e

