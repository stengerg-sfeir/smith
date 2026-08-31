import click
from account_service import AccountService
from database import Database

DB_PATH = "bank.db"

@click.group()
def cli():
    """Application root."""

@cli.command('customer-add')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--phone')
def customer_add(name, email, phone):
    """customer/add"""
    svc = AccountService(Database(DB_PATH))
    result = svc.add_customer(name=name, email=email, phone=phone)

@cli.command('account-deposit')
@click.option('--id', type=int, required=True)
def account_deposit(id):
    """account/deposit"""
    svc = AccountService(Database(DB_PATH))
    result = svc.deposit_account(id=id)

@cli.command('withdrawal-withdraw')
@click.option('--id', type=int, required=True)
def withdrawal_withdraw(id):
    """withdrawal/withdraw"""
    svc = AccountService(Database(DB_PATH))
    result = svc.withdraw_withdrawal(id=id)


if __name__ == "__main__":
    cli()

