"""Service layer."""
from __future__ import annotations

import datetime
from typing import Optional

from account_repository import AccountRepository
from customer_repository import CustomerRepository
from database import Database
from deposit_repository import DepositRepository
from exceptions import InsufficientFundsError, NotFoundError, ValidationError
from models import Customer, Deposit, Withdrawal
from withdrawal_repository import WithdrawalRepository


class AccountService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.account_repo = AccountRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.deposit_repo = DepositRepository(db)
        self.withdrawal_repo = WithdrawalRepository(db)

    def add_customer(self, name: str, email: str, phone: Optional[str] = None) -> bool:
        customer = Customer(name=name, email=email, phone=phone)
        return self.customer_repo.create(customer)

    def deposit_account(self, account_id: int, amount: float) -> bool:
        """Deposit money into an account."""
        try:
            account = self.account_repo.get_by_id(account_id)
            if not account:
                raise NotFoundError(f'Account with id {account_id} not found')
            customer = self.customer_repo.get_by_id(account.customer_id)
            if not customer:
                raise NotFoundError(f'Customer with id {account.customer_id} not found')
            if amount <= 0:
                raise ValidationError('Deposit amount must be positive')
            deposit = Deposit(account_id=account_id, amount=amount, created_at=datetime.datetime.now(), id=None)
            self.deposit_repo.create(deposit)
            self.account_repo.update(account_id, {'balance': account.balance + amount})
            return True
        except Exception as e:
            raise e

    def withdraw_withdrawal(self, account_id: int, amount: float) -> bool:
        """Withdraw money from an account."""
        try:
            account = self.account_repo.get_by_id(account_id)
            if not account:
                raise NotFoundError(f'Account with id {account_id} not found')
            customer = self.customer_repo.get_by_id(account.customer_id)
            if not customer:
                raise NotFoundError(f'Customer with id {account.customer_id} not found')
            if amount <= 0:
                raise ValidationError('Withdrawal amount must be positive')
            if account.balance < amount:
                raise InsufficientFundsError(f'Insufficient funds in account {account_id}. Current balance: {account.balance}, Requested: {amount}')
            withdrawal = Withdrawal(account_id=account_id, amount=amount, created_at=datetime.datetime.now(), id=None)
            self.withdrawal_repo.create(withdrawal)
            self.account_repo.update(account_id, {'balance': account.balance - amount})
            return True
        except Exception as e:
            raise e

