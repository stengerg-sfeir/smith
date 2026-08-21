import sqlite3

import click


@click.group()
def cli():
    """CLI for managing inventory operations."""
    pass

@cli.command()
@click.argument('item_id', type=click.INT, required=False)
@click.option('--name', prompt=True, help='Name of the item')
@click.option('--price', type=click.INT, help='Price in cents')
def add(item_id: Optional[int], name: str, price: Optional[int]):
    """Add a new item to inventory."""
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    cursor.execute('INSERT INTO items (id, name, price) VALUES (?, ?, ?)', (item_id, name, price))
    conn.commit()
    conn.close()
    click.echo(f"Item '{name}' added successfully.")

@cli.command()
@click.argument('item_id', type=click.INT, required=False)
@click.option('--name', help='Name of the item')
@click.option('--price', type=click.INT, help='Price in cents')
def update(item_id: Optional[int], name: Optional[str], price: Optional[int]):
    """Update an existing item in inventory."""
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    if name is not None:
        cursor.execute('UPDATE items SET name = ? WHERE id = ?', (name, item_id))
    if price is not None:
        cursor.execute('UPDATE items SET price = ? WHERE id = ?', (price, item_id))
    conn.commit()
    conn.close()
    click.echo(f"Item {item_id} updated successfully.")

@cli.command()
@click.argument('item_id', type=click.INT, required=False)
@click.option('--name', help='Name of the item')
@click.option('--price', type=click.INT, help='Price in cents')
def delete(item_id: Optional[int], name: Optional[str], price: Optional[int]):
    """Delete an item from inventory."""
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM items WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    click.echo(f"Item {item_id} deleted successfully.")

@cli.command()
@click.argument('item_id', type=click.INT, required=False)
def view(item_id: Optional[int]):
    """View item details or all items."""
    conn = sqlite3.connect('inventory.db')
    cursor = conn.cursor()
    if item_id is not None:
        cursor.execute('SELECT * FROM items WHERE id = ?', (item_id,))
    else:
        cursor.execute('SELECT * FROM items')
    rows = cursor.fetchall()
    conn.close()
    if rows:
        for row in rows:
            click.echo(f"ID: {row[0]}, Name: {row[1]}, Price: {row[2]} cents")
    else:
        click.echo("No items found.")

if __name__ == '__main__':
    cli()
