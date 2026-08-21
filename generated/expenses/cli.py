import click
from database import Database
from expense_service import ExpenseService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('category-add')
@click.option('--name', required=True)
@click.option('--description')
@click.option('--budget', type=int)
@click.option('--icon')
def category_add(name, description, budget, icon):
    """expense/category/add"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.add_expense(name=name, description=description, monthly_budget=budget, icon=icon)

@cli.command('category-list')
def category_list():
    """expense/category/list"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.list_expenses()

@cli.command('category-update')
@click.option('--id', type=int, required=True)
@click.option('--name')
@click.option('--description')
@click.option('--budget', type=int)
@click.option('--icon')
def category_update(id, name, description, budget, icon):
    """expense/category/update"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.update_expense(id=id, name=name, description=description, monthly_budget=budget, icon=icon)

@cli.command('category-delete')
@click.option('--id', type=int, required=True)
def category_delete(id):
    """expense/category/delete"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.delete_expense(id=id)

@cli.command('budget-list')
@click.option('--category', type=int)
@click.option('--month')
def budget_list(category, month):
    """budget/list"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.list_expenses(category_id=category, month=month)

@cli.command('budget-add')
@click.option('--category-id', type=int, required=True)
@click.option('--month', required=True)
@click.option('--amount', type=int, required=True)
def budget_add(category_id, month, amount):
    """budget/add"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.add_expense(category_id=category_id, month=month, amount_limit_cents=amount)

@cli.command('budget-update')
@click.option('--category-id', type=int, required=True)
@click.option('--month', required=True)
@click.option('--amount', type=int)
def budget_update(category_id, month, amount):
    """budget/update"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.update_expense(category_id=category_id, month=month, amount_limit_cents=amount)

@cli.command('budget-delete')
@click.option('--category-id', type=int, required=True)
@click.option('--month', required=True)
def budget_delete(category_id, month):
    """budget/delete"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.delete_expense(category_id=category_id, month=month)

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
    result = svc.add_expense(amount_cents=amount, description=description, category_id=category, expense_date=expense_date, payment_method=method, is_recurring=recurring)

@cli.command('expense-list')
@click.option('--category', type=int)
@click.option('--from-date')
@click.option('--to-date')
@click.option('--method')
def expense_list(category, from_date, to_date, method):
    """expense/list"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.list_expenses(category_id=category, start_date=from_date, end_date=to_date, payment_method=method)

@cli.command('report-monthly')
@click.option('--month', required=True)
def report_monthly(month):
    """expense/report/monthly"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.get_monthly_report(month=month)

@cli.command('report-yearly')
@click.option('--year', type=int, required=True)
def report_yearly(year):
    """expense/report/yearly"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.get_yearly_summary(year=year)

@cli.command('export-export')
@click.option('--from-date', required=True)
@click.option('--to-date', required=True)
@click.option('--output', required=True)
def export_export(from_date, to_date, output):
    """expense/export/export"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.export_to_csv(start_date=from_date, end_date=to_date, file_path=output)

@cli.command('recurring-detect')
def recurring_detect():
    """expense/recurring/detect"""
    svc = ExpenseService(Database(DB_PATH))
    result = svc.detect_recurring()


if __name__ == "__main__":
    cli()

