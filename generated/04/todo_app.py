#!/usr/bin/env python3
import click
import sqlite3
from typing import Optional

@click.group()
def cli():
    """A simple command-line todo application."""
    pass

@cli.command()
@click.argument('task', required=True)
def add(task: str):
    """Add a new task."""
    with sqlite3.connect('todo.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO tasks (description) VALUES (?)", (task,))
        conn.commit()
    click.echo(f"Task '{task}' added successfully.")

@cli.command()
def list_tasks():
    """List all tasks."""
    with sqlite3.connect('todo.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, description, completed FROM tasks ORDER BY id")
        tasks = cursor.fetchall()
    if not tasks:
        click.echo("No tasks found.")
    else:
        for task in tasks:
            task_id, description, completed = task
            status = "✓" if completed else "✗"
            click.echo(f"{task_id}. [{status}] {description}")

@cli.command()
@click.argument('task_id', type=int, required=True)
def complete(task_id: int):
    """Mark a task as complete."""
    with sqlite3.connect('todo.db') as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE tasks SET completed = 1 WHERE id = ?", (task_id,))
        conn.commit()
    click.echo(f"Task {task_id} marked as complete.")

@cli.command()
@click.argument('task_id', type=int, required=True)
def delete(task_id: int):
    """Delete a task by ID."""
    with sqlite3.connect('todo.db') as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
    click.echo(f"Task {task_id} deleted.")

@cli.command()
def init_db():
    """Initialize the database with a tasks table."""
    with sqlite3.connect('todo.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                completed INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
    click.echo("Database initialized.")

if __name__ == '__main__':
    cli()
