#!/usr/bin/env python3
import click
import sqlite3

@click.command()
@click.argument('num1', type=float)
@click.argument('num2', type=float)
@click.argument('operation', type=click.Choice(['add', 'subtract', 'multiply', 'divide']))
def main(num1: float, num2: float, operation: str):
    """
    A simple CLI calculator that supports addition, subtraction, multiplication, and division.
    """
    try:
        if operation == 'add':
            result = num1 + num2
        elif operation == 'subtract':
            result = num1 - num2
        elif operation == 'multiply':
            result = num1 * num2
        elif operation == 'divide':
            if num2 == 0:
                click.echo("Error: Division by zero is not allowed.", err=True)
                return
            result = num1 / num2
        else:
            click.echo("Error: Invalid operation.", err=True)
            return
        click.echo(f"Result: {result}")
    except Exception as e:
        click.echo(f"Error: {str(e)}", err=True)

if __name__ == '__main__':
    main()
