import click
from database import Database
from expense_service import ExpenseService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('category-add')
@click.option('--name', required=True)
@click.option('--description', required=True)
@click.option('--budget')
@click.option('--icon')
def category_add(name, description, budget, icon):
    """expense/category/add"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.add_category(name=name, description=description, budget=budget, icon=icon)

@cli.command('category-list')
def category_list():
    """expense/category/list"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.list_category()

@cli.command('category-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--budget')
@click.option('--icon')
def category_update(id, name, description, budget, icon):
    """expense/category/update"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.update_category(id=id, name=name, description=description, budget=budget, icon=icon)

@cli.command('category-delete')
@click.option('--id', type=int, required=True)
def category_delete(id):
    """expense/category/delete"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.delete_category(id=id)

@cli.command('budget-list')
@click.option('--category', type=int)
@click.option('--month')
def budget_list(category, month):
    """budget/list"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.list_budget(category_id=category, month=month)

@cli.command('budget-add')
@click.option('--category-id', type=int, required=True)
@click.option('--month', required=True)
@click.option('--amount', type=int, required=True)
def budget_add(category_id, month, amount):
    """budget/add"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.add_budget(category_id=category_id, month=month, amount_limit_cents=amount)

@cli.command('budget-update')
@click.option('--category-id', type=int, required=True)
@click.option('--month', required=True)
@click.option('--amount', type=int)
def budget_update(category_id, month, amount):
    """budget/update"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.update_budget(category_id=category_id, month=month, amount_limit_cents=amount)

@cli.command('budget-delete')
@click.option('--category-id', type=int, required=True)
@click.option('--month', required=True)
def budget_delete(category_id, month):
    """budget/delete"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.delete_budget(category_id=category_id, month=month)

@cli.command('expense-add')
@click.option('--amount', type=int, required=True)
@click.option('--description', required=True)
@click.option('--category', type=int, required=True)
@click.option('--expense-date')
@click.option('--method')
@click.option('--recurring', is_flag=True, default=False)
def expense_add(amount, description, category, expense_date, method, recurring):
    """expense/add"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.add(amount_cents=amount, description=description, category_id=category, expense_date=expense_date, payment_method=method, is_recurring=recurring)

@cli.command('expense-list')
@click.option('--category', type=int)
@click.option('--from-date')
@click.option('--to-date')
@click.option('--method')
def expense_list(category, from_date, to_date, method):
    """expense/list"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.list(category_id=category, from_date=from_date, to_date=to_date, payment_method=method)

@cli.command('report-monthly')
@click.option('--month', required=True)
def report_monthly(month):
    """expense/report/monthly"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.report(month=month)

@cli.command('expense-export')
@click.option('--from-date', required=True)
@click.option('--to-date', required=True)
@click.option('--output', required=True)
def expense_export(from_date, to_date, output):
    """expense/export"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.export(from_date=from_date, to_date=to_date, output=output)

@cli.command('expense-recurring')
def expense_recurring():
    """expense/recurring"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.detect_recurring()


if __name__ == "__main__":
    cli()

