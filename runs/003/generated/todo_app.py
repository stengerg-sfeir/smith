#!/usr/bin/env python3
import click
import sqlite3
from typing import Optional, List

@click.group()
def cli():
    """A simple command-line todo application."""
    pass

@cli.command()
@click.argument('task', required=True)
def add(task: str):
    """Add a new task."""
    # In-memory storage (simulated)
    tasks = []
    # In a real app, we'd use a database here
    tasks.append({'id': len(tasks) + 1, 'task': task, 'completed': False})
    click.echo(f"Task '{task}' added successfully.")

@cli.command()
def list_tasks():
    """List all tasks."""
    tasks = []
    # In a real app, we'd query the database
    click.echo("Tasks:")
    for task in tasks:
        status = "✓" if task['completed'] else "✗"
        click.echo(f"{status} {task['task']}")

@cli.command()
@click.argument('task_id', type=int, required=True)
def complete(task_id: int):
    """Mark a task as completed."""
    tasks = []
    # In a real app, we'd query the database
    for task in tasks:
        if task['id'] == task_id:
            task['completed'] = True
            click.echo(f"Task {task_id} marked as completed.")
            return
    click.echo(f"Task {task_id} not found.")

@cli.command()
@click.argument('task_id', type=int, required=True)
def delete(task_id: int):
    """Delete a task."""
    tasks = []
    # In a real app, we'd query the database
    for i, task in enumerate(tasks):
        if task['id'] == task_id:
            tasks.pop(i)
            click.echo(f"Task {task_id} deleted.")
            return
    click.echo(f"Task {task_id} not found.")

if __name__ == '__main__':
    cli()
