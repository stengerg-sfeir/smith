import click
from database import Database
from employee_service import EmployeeService

DB_PATH = "app.db"

@click.group()
def cli():
    """Application root."""

@cli.command('employee-create')
@click.option('--name', required=True)
@click.option('--email', required=True)
@click.option('--age', type=int, required=True)
@click.option('--salary', type=int, required=True)
def employee_create(name, email, age, salary):
    """employee/create"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.create_employee(name=name, email=email, age=age, salary=salary)

@cli.command('get-by_email')
@click.option('--email', required=True)
def get_by_email(email):
    """employee/get/by_email"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employee_by_email(email=email)

@cli.command('get-by_age_range')
@click.option('--min-age', type=int, required=True)
@click.option('--max-age', type=int, required=True)
def get_by_age_range(min_age, max_age):
    """employee/get/by_age_range"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employees_by_age_range(min_age=min_age, max_age=max_age)

@cli.command('get-with_salary_above')
@click.option('--min-salary', type=int, required=True)
def get_with_salary_above(min_salary):
    """employee/get/with_salary_above"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employees_with_salary_above(min_salary=min_salary)

@cli.command('get-with_salary_in_range')
@click.option('--min-salary', type=int, required=True)
@click.option('--max-salary', type=int, required=True)
def get_with_salary_in_range(min_salary, max_salary):
    """employee/get/with_salary_in_range"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employees_with_salary_in_range(min_salary=min_salary, max_salary=max_salary)

@cli.command('get-with_valid_email_and_age_range')
@click.option('--min-age', type=int, required=True)
@click.option('--max-age', type=int, required=True)
def get_with_valid_email_and_age_range(min_age, max_age):
    """employee/get/with_valid_email_and_age_range"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employees_with_valid_email_and_age_range(min_age=min_age, max_age=max_age)

@cli.command('stats-age_group_count')
def stats_age_group_count():
    """employee/stats/age_group_count"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.count_employees_by_age_group()

@cli.command('stats-average_salary')
def stats_average_salary():
    """employee/stats/average_salary"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_average_salary()

@cli.command('stats-total_salary')
def stats_total_salary():
    """employee/stats/total_salary"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_total_salary_spent()

@cli.command('stats-above_average')
def stats_above_average():
    """employee/stats/above_average"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.get_employees_with_higher_salary_than_average()

@cli.command('export-to_csv')
@click.option('--file-path', required=True)
def export_to_csv(file_path):
    """employee/export/to_csv"""
    svc = EmployeeService(Database(DB_PATH))
    result = svc.export_employees_to_csv(file_path=file_path)


if __name__ == "__main__":
    cli()

