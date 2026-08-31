import click
from account_service import AccountService
from database import Database

DB_PATH = "bank.db"

@click.group()
def cli():
    """Application root."""

@cli.command('deposit-create')
@click.option('--account-id', type=int, required=True)
@click.option('--amount', type=int, required=True)
def deposit_create(account_id, amount):
    """account/deposit/create"""
    svc = AccountService(Database(DB_PATH))
    result = svc.create_deposit(account_id=account_id, amount=amount)

@cli.command('withdrawal-create')
@click.option('--account-id', type=int, required=True)
@click.option('--amount', type=int, required=True)
def withdrawal_create(account_id, amount):
    """account/withdrawal/create"""
    svc = AccountService(Database(DB_PATH))
    result = svc.create_withdrawal(account_id=account_id, amount=amount)

@cli.command('balance-with_transaction_count')
@click.option('--account-id', type=int, required=True)
def balance_with_transaction_count(account_id):
    """account/balance/with_transaction_count"""
    svc = AccountService(Database(DB_PATH))
    result = svc.get_account_balance_with_transaction_count(account_id=account_id)

@cli.command('summary-customer')
@click.option('--customer-id', type=int, required=True)
@click.option('--min-balance', type=int)
@click.option('--max-balance', type=int)
def summary_customer(customer_id, min_balance, max_balance):
    """account/summary/customer"""
    svc = AccountService(Database(DB_PATH))
    result = svc.get_customer_accounts_summary(customer_id=customer_id, min_balance=min_balance, max_balance=max_balance)

@cli.command('export-transactions')
@click.option('--account-id', type=int, required=True)
@click.option('--file-path', required=True)
def export_transactions(account_id, file_path):
    """account/export/transactions"""
    svc = AccountService(Database(DB_PATH))
    result = svc.export_account_transactions_to_csv(account_id=account_id, file_path=file_path)

@cli.command('risk-negative_after_withdrawal')
@click.option('--account-id', type=int, required=True)
@click.option('--withdrawal-amount', type=int, required=True)
def risk_negative_after_withdrawal(account_id, withdrawal_amount):
    """account/risk/negative_after_withdrawal"""
    svc = AccountService(Database(DB_PATH))
    result = svc.find_accounts_with_negative_balance_after_withdrawal(account_id=account_id, withdrawal_amount=withdrawal_amount)

@cli.command('total-total_balance')
def total_total_balance():
    """account/total/total_balance"""
    svc = AccountService(Database(DB_PATH))
    result = svc.get_total_balance_by_customer()


if __name__ == "__main__":
    cli()

