import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    """SQLite database wrapper with automatic table creation."""

    def __init__(self, db_path: str = ":memory:"):
        """Initialize connection path and create tables."""
        self.db_path = db_path
        if db_path != ":memory:":
            parent = Path(db_path).parent
            if parent and not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def connect(self) -> sqlite3.Connection:
        """Open a new connection with foreign keys enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_tables(self) -> None:
        """Create all required tables if they do not exist."""
        with self.connect() as conn:
            create_tables(conn)


def get_db_connection(db_path: str = ":memory:") -> sqlite3.Connection:
    """Create a new database connection with foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_connection(db_path: str = ":memory:"):
    """Context manager for database connection."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_tables(conn: sqlite3.Connection) -> None:
    """Create all required tables."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.executescript(
        """        CREATE TABLE IF NOT EXISTS customers (
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT,
            UNIQUE(email)
        );

        CREATE TABLE IF NOT EXISTS accounts (
            customer_id INTEGER NOT NULL,
            balance REAL NOT NULL,
            created_at TEXT NOT NULL,
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        );

        CREATE TABLE IF NOT EXISTS deposits (
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        );

        CREATE TABLE IF NOT EXISTS withdrawals (
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            created_at TEXT NOT NULL,
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        );"""
    )
    conn.commit()


def init_database(db_path: str = "bank.db") -> sqlite3.Connection:
    """Initialize database with tables and return connection."""
    conn = get_db_connection(db_path)
    create_tables(conn)
    return conn
