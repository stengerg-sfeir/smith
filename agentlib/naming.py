"""Naming and SQL/DDL helpers.

Extracted from agent.py. Pure string/type mappings plus deterministic
CREATE TABLE / database.py generation from model AST field lists.
"""
import re


def _snake(s):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def _camel(s):
    # Split on underscores/spaces, then on existing camelCase boundaries so
    # already-PascalCase tokens (e.g. CategoryNotFoundError) survive intact
    # instead of collapsing to "Categorynotfounderror".
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    return "".join(p.capitalize() for p in re.split(r"[_\s]+", s) if p)


def _plural(e):
    if e.endswith("y") and len(e) > 1 and e[-2] not in "aeiou":
        return e[:-1] + "ies"
    return e + "s"


def _bare(t):
    return (t or "").replace("Optional[", "").replace("]", "").strip()


def _pluralize_table_name(class_name):
    """Singular class name -> plural lowercase table name.

    box -> boxes, city -> cities, task -> tasks.
    """
    lower = class_name.lower()
    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        return lower[:-1] + "ies"
    if lower.endswith("s"):
        return lower + "es"
    return lower + "s"


def _entity_table_name(ent):
    """Declared table name when the design declares one (irregular plural),
    else the deterministic rule over the class name."""
    ent = ent or {}
    tn = (ent.get("table_name") or "").strip()
    return tn or _pluralize_table_name(ent.get("name") or "")


def _python_type_to_sql(type_hint):
    """Map Python type hints to SQLite column types."""
    t = type_hint.lower()
    if "int" in t:
        return "INTEGER"
    if "bool" in t:
        return "BOOLEAN"
    if "str" in t or "text" in t or "string" in t:
        return "TEXT"
    if "float" in t or "decimal" in t:
        return "REAL"
    return "TEXT"


def _sql_literal(value):
    """A SQL literal for a model field's declared default, or None.

    Only a literal the dataclass actually declared reaches here, and SQLite
    stores booleans as 0/1, so ``is_active: bool = True`` becomes ``DEFAULT 1``
    — the same value the dataclass constructor would apply.
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return "'%s'" % value.replace("'", "''")
    return None


def _generate_ddl_from_models(model_classes):
    """Generate CREATE TABLE DDL from model class definitions.

    Model class names become table names (lowercase pluralized).
    Fields become columns. 'id' fields get PRIMARY KEY AUTOINCREMENT.
    Table-level UNIQUE pairs come from the models' UNIQUE_TOGETHER constant.
    A field carrying a declared literal default ALSO gets that default in the
    column (``available_copies INTEGER NOT NULL DEFAULT 1``, ``is_active
    BOOLEAN NOT NULL DEFAULT 1``): the specification states the default, the
    dataclass applies it, and a plain INSERT that omits the column must land
    on the same value instead of failing the NOT NULL constraint.
    """
    unique_map = model_classes.pop("__unique_together__", {})
    table_map = model_classes.pop("__table_names__", {})
    default_map = model_classes.pop("__field_defaults__", {})
    tables = []

    for class_name, fields in model_classes.items():
        table_name = table_map.get(class_name) or _pluralize_table_name(class_name)

        columns = []
        foreign_keys = []
        unique_constraints = []
        for pair in unique_map.get(class_name) or []:
            cols_sql = ", ".join(str(c) for c in pair)
            unique_constraints.append("    UNIQUE(%s)" % cols_sql)

        for field_name, type_hint in fields:
            sql_type = _python_type_to_sql(type_hint)
            col_def = "    %s %s" % (field_name, sql_type)

            if field_name == "id":
                col_def += " PRIMARY KEY AUTOINCREMENT"
            elif "Optional" in type_hint:
                # Allow NULL for Optional fields
                pass
            else:
                col_def += " NOT NULL"

            if field_name != "id":
                literal = _sql_literal(
                    (default_map.get(class_name) or {}).get(field_name)
                )
                if literal is not None:
                    col_def += " DEFAULT %s" % literal

            columns.append(col_def)

            # Detect foreign key patterns. A HISTORY table is exempt: its
            # reference column is historical data, not a live relationship,
            # and ``ON DELETE CASCADE`` would erase the record of the very
            # deletion it exists to log — worse, the delete's own audit row
            # could never survive it (prompt 33: an audit record must be
            # produced for every deletion). The design names its history
            # table "Audit*" / "Log*" / "History*", which is the signal here;
            # the id column itself is kept, as the historical reference.
            _history = any(
                word in str(class_name).lower()
                for word in ("audit", "history", "log")
            )
            if field_name.endswith("_id") and field_name != "id" and not _history:
                base = field_name[: -len("_id")]
                ref_table = table_map.get(_camel(base)) or _pluralize_table_name(base)
                foreign_keys.append(
                    "    FOREIGN KEY (%s) REFERENCES %s (id) ON DELETE CASCADE" % (field_name, ref_table)
                )

        # Build CREATE TABLE (terminate with ';' so executescript
        # splits statements correctly)
        all_parts = columns + foreign_keys + unique_constraints
        ddl = "CREATE TABLE IF NOT EXISTS %s (\n%s\n);" % (
            table_name,
            ",\n".join(all_parts)
        )
        tables.append(ddl)

    return "\n\n".join(tables)


def _generate_database_file(model_classes, db_filename="app.db"):
    """Generate a complete database.py from model AST definitions.

    Uses a list-based template to guarantee clean line indentation --
    no dedent/tab pitfalls. DDL is emitted via cursor.executescript()
    with a triple-quoted string, so column/table lines never become
    bare statements inside the function body.

    The module emits EXACTLY the surface a generated project needs: the
    ``Database`` class (the only entry point the repositories, the service and
    main.py construct) and ``create_tables`` (called by ``Database._init_tables``).
    Three helpers used to be emitted beside them — ``get_db_connection``,
    ``get_connection`` and ``init_database`` — and NOTHING in any generated
    project, harness or specification ever called them: three spellings of one
    connection, over-generated exactly like an unrequested CLI command. The
    spec's own SQLite filename still reaches the file, as its module docstring.
    """
    ddl = _generate_ddl_from_models(model_classes)

    # Indent each DDL line by 8 spaces (continuation of the string arg)
    indented_ddl = "\n".join("        " + line if line.strip() else line
                             for line in ddl.split("\n"))

    lines = [
        '"""SQLite storage layer. Canonical database file: %s."""' % db_filename,
        "import sqlite3",
        "from contextlib import contextmanager",
        "from pathlib import Path",
        "",
        "",
        "class IntegrityViolation(Exception):",
        '    """A write the store refused (a constraint the data violated).',
        "",
        "    The persistence layer owns the driver, so it owns the driver's",
        "    failures: a caller above it catches a DOMAIN error and never has",
        '    to import sqlite3 to do so."""',
        "",
        "",
        "class Database:",
        '    """SQLite database wrapper with automatic table creation."""',
        "",
        '    def __init__(self, db_path: str = "%s"):' % db_filename,
        '        """Initialize connection path and create tables."""',
        "        self.db_path = db_path",
        '        if db_path != ":memory:":',
        "            parent = Path(db_path).parent",
        "            if parent and not parent.exists():",
        "                parent.mkdir(parents=True, exist_ok=True)",
        "        self._init_tables()",
        "",
        "    @contextmanager",
        "    def connect(self):",
        '        """Yield a connection with foreign keys on, then CLOSE it."""',
        "        conn = sqlite3.connect(self.db_path)",
        "        conn.row_factory = sqlite3.Row",
        '        conn.execute("PRAGMA foreign_keys = ON")',
        "        try:",
        "            yield conn",
        "            conn.commit()",
        "        except sqlite3.IntegrityError as exc:",
        "            conn.rollback()",
        "            raise IntegrityViolation(str(exc)) from exc",
        "        except Exception:",
        "            conn.rollback()",
        "            raise",
        "        finally:",
        "            conn.close()",
        "",
        '    def _init_tables(self) -> None:',
        '        """Create all required tables if they do not exist."""',
        "        with self.connect() as conn:",
        "            create_tables(conn)",
        "",
        "",
        "def create_tables(conn: sqlite3.Connection) -> None:",
        '    """Create all required tables."""',
        "    cursor = conn.cursor()",
        '    cursor.execute("PRAGMA foreign_keys = ON")',
        "    cursor.executescript(",
        '        """' + indented_ddl + '"""',
        "    )",
        "    conn.commit()",
    ]
    return "\n".join(lines)
