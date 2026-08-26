"""Service layer."""
from __future__ import annotations

import csv
from typing import Any, Dict

from account_repository import AccountRepository
from customer_repository import CustomerRepository
from database import Database
from exceptions import InsufficientFundsError, NotFoundError
from models import Account


class AccountService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.account_repo = AccountRepository(db)
        self.customer_repo = CustomerRepository(db)

    def create_deposit(self, account_id: int, amount: float) -> bool:
        # Deposit handling is not implemented due to missing deposit_repository
        # This method is currently a placeholder
        return False

    def process_withdrawal(self, account_id: int, amount: float) -> bool:
        account = self.account_repo.get_by_id(account_id)
        if not account:
            raise NotFoundError(f'Account with id {account_id} not found')
        customer = self.customer_repo.get_by_id(account.customer_id)
        if not customer:
            raise NotFoundError(f'Customer with id {account.customer_id} not found')
        current_balance = account.balance
        if current_balance < amount:
            raise InsufficientFundsError(f'Insufficient funds. Current balance: {current_balance}, Requested withdrawal: {amount}')
        new_balance = current_balance - amount
        account.balance = new_balance
        self.account_repo.update(account_id, {'balance': new_balance})
        return True

    def get_account_balance_with_transaction_count(self, account_id: int) -> dict[str, Any]:
        return self.account_repo.get_account_balance_with_transaction_count(account_id)

    def get_accounts_with_recent_activity(self, days_ago: int, threshold_amount: float) -> list[Account]:
        return self.account_repo.get_accounts_with_recent_activity(days_ago=days_ago, threshold_amount=threshold_amount)

    def export_account_transactions_to_csv(self, account_id: int, file_path: str) -> None:
        # Filter transactions for the specific account_id
        rows = self.account_repo.list()
        # Filter rows to only include the specified account
        filtered_rows = [row for row in rows if row.id == account_id]
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                'id', 'customer_id', 'balance', 'created_at',
            ])
            for row in filtered_rows:
                writer.writerow([
                    row.id, row.customer_id, row.balance, row.created_at,
                ])

    def get_customer_accounts_summary(self) -> Dict[str, Any]:
        """Returns a summary of customer accounts including total accounts, total balance, and average balance."""
        customer_accounts = self.customer_repo.list()
        total_accounts = len(customer_accounts)
        total_balance = sum(account.balance for account in customer_accounts)
        average_balance = total_balance / total_accounts if total_accounts > 0 else 0
        return {
            "total_accounts": total_accounts,
            "total_balance": total_balance,
            "average_balance": average_balance
        }

    def get_total_deposits_and_withdrawals_by_account(self) -> Dict[int, Dict[str, float]]:
        """Returns a dictionary mapping account IDs to total deposits and withdrawals."""
        # This method aggregates deposits and withdrawals by account ID
        # Assuming the repository can provide transaction data
        account_transactions = self.account_repo.list()
        account_deposits = {}
        account_withdrawals = {}

        for transaction in account_transactions:
            if transaction.account_id not in account_deposits:
                account_deposits[transaction.account_id] = 0
            if transaction.account_id not in account_withdrawals:
                account_withdrawals[transaction.account_id] = 0

            # Assuming transaction type is either 'deposit' or 'withdrawal'
            if transaction.type == 'deposit':
                account_deposits[transaction.account_id] += transaction.amount
            elif transaction.type == 'withdrawal':
                account_withdrawals[transaction.account_id] += transaction.amount

        # Combine deposits and withdrawals into a single result
        result = {}
        for account_id in account_deposits:
            result[account_id] = {
                "total_deposits": account_deposits[account_id],
                "total_withdrawals": account_withdrawals.get(account_id, 0)
            }
        return result
