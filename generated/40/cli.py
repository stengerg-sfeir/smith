import sqlite3
from typing import Optional

import click


@click.group()
def cli():
    """Command-line interface for the application."""
    pass


@cli.command()
@click.option('--id', type=click.INT, help='ID of the record to retrieve')
def get(id: Optional[int]):
    """Retrieve a record by ID."""
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    query = "SELECT * FROM records WHERE id = ?"
    cursor.execute(query, (id,))
    result = cursor.fetchone()

    if result:
        click.echo(f"Record: {result}")
    else:
        click.echo("Record not found.")

    conn.close()


@cli.command()
@click.option('--id', type=click.INT, help='ID of the record to update')
@click.option('--money', type=click.INT, help='Money value in cents to update')
def update(id: Optional[int], money: int):
    """Update a record's money value."""
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    query = "UPDATE records SET money = ? WHERE id = ?"
    cursor.execute(query, (money, id))

    if cursor.rowcount == 0:
        click.echo("No record found to update.")
    else:
        click.echo("Record updated successfully.")

    conn.commit()
    conn.close()


@cli.command()
@click.option('--id', type=click.INT, help='ID of the record to delete')
def delete(id: Optional[int]):
    """Delete a record by ID."""
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    query = "DELETE FROM records WHERE id = ?"
    cursor.execute(query, (id,))

    if cursor.rowcount == 0:
        click.echo("No record found to delete.")
    else:
        click.echo("Record deleted successfully.")

    conn.commit()
    conn.close()


@cli.command()
def list_records():
    """List all records."""
    conn = sqlite3.connect('app.db')
    cursor = conn.cursor()

    query = "SELECT * FROM records"
    cursor.execute(query)
    records = cursor.fetchall()

    if records:
        for record in records:
            click.echo(f"ID: {record[0]}, Money: {record[1]} cents")
    else:
        click.echo("No records found.")

    conn.close()


if __name__ == '__main__':
    cli()
