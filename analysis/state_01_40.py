"""State of the numbered prompts: one functional probe per prompt.

Run from the repository root AFTER regenerating 01..40:

    python3 /tmp/state_01_40.py            # all
    python3 /tmp/state_01_40.py 31 32      # some

Each probe drives the generated CLI and asserts what the prompt explicitly
asks for. It prints one line per check (PASS/FAIL) and a verdict per prompt.
The point is to measure the SHIPPED application, so a probe never looks at the
generator's internals.
"""
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

NOT_ENTRY = {"models", "database", "exceptions"}
HELPER_SUFFIXES = ("_repository", "_service", "_repo", "_interface")
RESULTS = []


def entry_of(project):
    for name in ("main.py", "app.py", "cli.py"):
        if (project / name).exists():
            return (project / name).resolve()
    scripts = [
        path for path in sorted(project.glob("*.py"))
        if path.stem not in NOT_ENTRY
        and not path.stem.endswith(HELPER_SUFFIXES)
        and path.name != "__main__.py"
    ]
    return scripts[0].resolve() if len(scripts) == 1 else None


def fresh(number):
    """A clean database, so ids and totals are predictable."""
    project = Path("generated") / number
    for db in project.glob("*.db"):
        db.unlink()
    return project


def cli(project, *args, timeout=60):
    """Run the generated application; returns (rc, stdout, stderr)."""
    entry = entry_of(project)
    if entry is None:
        return "no-entry", "", ""
    try:
        proc = subprocess.run(
            [sys.executable, str(entry), *[str(a) for a in args]],
            capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, cwd=str(project),
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return "timeout", "", ""


def sql(project, statement):
    """Every row of every ``*.db`` of the project, concatenated."""
    rows = []
    for db in sorted(project.glob("*.db")):
        conn = sqlite3.connect(db)
        try:
            rows.extend(conn.execute(statement).fetchall())
        except sqlite3.Error as exc:
            rows.append(("ERROR", str(exc)))
        finally:
            conn.close()
    return rows


def execute(project, statement):
    """Run one statement against the application's database, COMMITTED.

    ``sql`` opens a connection and closes it without committing, which is
    exactly right for a SELECT and silently useless for an INSERT (sqlite3
    rolls an uncommitted transaction back on close). A probe that seeds rows
    itself needs the write to survive the process.
    """
    for db in sorted(project.glob("*.db")):
        conn = sqlite3.connect(db)
        try:
            conn.execute(statement)
            conn.commit()
        except sqlite3.Error as exc:
            return str(exc)
        finally:
            conn.close()
    return None


def check(label, ok, detail=""):
    RESULTS.append(ok)
    print("    %s %s%s" % ("PASS" if ok else "FAIL", label,
                          (" | " + detail[:160]) if detail else ""))


def contains(text, needle):
    return needle.lower() in (text or "").lower()


# Values used to satisfy whatever required options a command declares. The
# generator invents field names, so a probe that hard-codes them measures its
# own guesses instead of the application.
VALUES = {
    "title": "T", "name": "N", "first-name": "F", "last-name": "L",
    "email": "e@x.com", "phone": "1", "address": "A", "city": "C",
    "state": "S", "postal-code": "1", "zip-code": "1", "country": "X",
    "description": "D", "price": "10", "quantity": "1", "amount": "10",
    "status": "pending", "priority": "high", "isbn": "1",
    "publication-year": "2000", "sku": "S1", "category": "general",
    "stock-quantity": "5", "balance": "100", "account-type": "checking",
    "customer-id": "1", "user-id": "1", "project-id": "1",
    "department-id": "1", "book-id": "1", "member-id": "1", "room-id": "1",
    "product-id": "1", "order-id": "1", "invoice-id": "1", "task-id": "1",
    "post-id": "1", "customer-name": "C", "owner-name": "O",
    "total-amount": "10", "order-date": "2026-01-01", "due-date": "2026-02-01",
    "start-date": "2026-01-01", "end-date": "2026-01-05",
    "created-at": "2026-01-01", "hire-date": "2026-01-01", "capacity": "2",
    "location": "L", "manufacturer": "M", "model": "M", "year": "2000",
    "license-plate": "P", "role": "user", "password-hash": "h",
    "author": "A", "member-name": "M", "room-number": "101", "floor": "1",
}


def add_row(project, group, **overrides):
    """Create one row of ``group``, filling the options its OWN help requires.

    Returns ``(rc, out, err)``. Only REQUIRED options are filled, so a command
    that accepts extra fields stays exercisable; an option with no known value
    is left out, which shows up as click's own "Missing option" error rather
    than as a probe passing by accident.
    """
    help_text = cli(project, group, "add", "--help")[1]
    argv = [group, "add"]
    required = re.findall(r"^\s*--([\w-]+)\s+\S+\s+\[required\]", help_text, re.M)
    for option in required:
        key = option.replace("-", "_")
        value = overrides.get(key, VALUES.get(option))
        if value is None:
            continue
        argv += ["--%s" % option, str(value)]
    return cli(project, *argv)


def module_run(project, module, *args):
    """Run ``python -m <module>`` inside the project (a package entry point)."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", module, *[str(a) for a in args]],
            capture_output=True, text=True, timeout=60,
            stdin=subprocess.DEVNULL, cwd=str(project),
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return "timeout", "", ""


def surface(project):
    """The top-level ``--help`` of the application, for the record."""
    rc, out, err = cli(project, "--help")
    return out or err


def probe_01():
    project = fresh("01")
    rc, out, err = module_run(project, "hello")
    detail = out or err
    check("python -m hello runs", rc == 0, "rc=%s %s" % (rc, detail))


def probe_02():
    project = fresh("02")
    rc, out, err = cli(project, "7", "2", "divide")
    zero = cli(project, "5", "0", "divide")
    check("division by zero is reported clearly",
          "zero" in (zero[1] + zero[2]).lower(),
          "rc=%s out=%s err=%s" % zero)
    check("7 / 2 is 3.5, not 3 (integers only otherwise)",
          contains(out, "3.5"), "rc=%s out=%s err=%s" % (rc, out, err))


def probe_03():
    project = fresh("03")
    rc, out, err = cli(project, "--list")
    check("--list runs without demanding input", rc == 0,
          "rc=%s out=%s err=%s" % (rc, out, err))


def probe_04():
    project = fresh("04")
    cli(project, "add", "write tests")
    rc, out, err = cli(project, "list-tasks")
    check("a task can be added and listed", "write tests" in out,
          "rc=%s out=%s err=%s" % (rc, out, err))


def probe_05():
    project = fresh("05")
    cli(project, "contact", "add", "--name", "Alice", "--email", "a@x.com")
    cli(project, "contact", "add", "--name", "Bob", "--email", "b@x.com")
    check("update lands", cli(project, "contact", "update", "--id", "1",
                              "--name", "Alice2")[0] == 0 and
          "Alice2" in cli(project, "contact", "list")[1])
    check("delete lands", cli(project, "contact", "delete", "--id", "2")[0] == 0
          and len(sql(project, "SELECT * FROM contacts")) == 1)


def probe_06():
    project = fresh("06")
    cli(project, "product", "add", "--name", "W", "--price", "10")
    check("create + update + delete",
          "W" in cli(project, "product", "list")[1]
          and cli(project, "product", "update", "--id", "1",
                  "--price", "12")[0] == 0
          and cli(project, "product", "delete", "--id", "1")[0] == 0
          and cli(project, "product", "list")[1] == "[]")


def probe_07():
    project = fresh("07")
    cli(project, "book", "add", "--title", "The Ring", "--author", "Tolkien",
        "--isbn", "1", "--publication-year", "1954")
    cli(project, "book", "add", "--title", "Other", "--author", "X",
        "--isbn", "2", "--publication-year", "2000")
    rc, out, err = cli(project, "book", "search", "--term", "Ring")
    check("search returns only the matching book",
          "The Ring" in out and "Other" not in out,
          "rc=%s out=%s err=%s" % (rc, out, err))


def probe_08():
    project = fresh("08")
    cli(project, "product", "add", "--name", "A", "--category", "tools",
        "--price", "10", "--quantity", "5")
    cli(project, "product", "add", "--name", "B", "--category", "food",
        "--price", "20", "--quantity", "1")
    check("category filter", cli(project, "product", "list",
                                 "--category", "tools")[1].count("Product(") == 1)
    check("below-threshold filter",
          cli(project, "product", "list", "--threshold", "3")[1].count("Product(") == 1)


def probe_09():
    project = fresh("09")
    invalid = [
        ("email must be valid",
         ("employee", "add", "--name", "X", "--email", "nope", "--age", "30",
          "--salary", "100")),
        ("age 17 refused",
         ("employee", "add", "--name", "X", "--email", "a@x.com", "--age", "17",
          "--salary", "100")),
        ("age 71 refused",
         ("employee", "add", "--name", "X", "--email", "a@x.com", "--age", "71",
          "--salary", "100")),
        ("negative salary refused",
         ("employee", "add", "--name", "X", "--email", "a@x.com", "--age", "30",
          "--salary", "-5")),
    ]
    for label, argv in invalid:
        rc, out, err = cli(project, *argv)
        check(label, rc != 0, "rc=%s err=%s" % (rc, err))
    check("a valid employee is accepted",
          cli(project, "employee", "add", "--name", "D", "--email", "d@x.com",
              "--age", "30", "--salary", "100")[0] == 0
          and len(sql(project, "SELECT * FROM employees")) == 1)


def probe_10():
    project = fresh("10")
    names = {path.stem for path in project.glob("*.py")}
    check("modules are split (model/persistence/service/cli)",
          {"models", "database"} <= names
          and any(name.endswith(("_service", "_repository")) for name in names),
          str(sorted(names)))
    check("note CRUD",
          cli(project, "note", "add", "--title", "T", "--content", "C")[0] == 0
          and "T" in cli(project, "note", "list")[1]
          and cli(project, "note", "update", "--id", "1", "--title", "T2")[0] == 0
          and cli(project, "note", "delete", "--id", "1")[0] == 0)


def probe_11():
    project = fresh("11")
    cli(project, "book", "add", "--title", "X", "--author", "A", "--isbn", "I1",
        "--publication-year", "2000")
    rc, out, err = cli(project, "book", "add", "--title", "Y", "--author", "B",
                       "--isbn", "I1", "--publication-year", "2001")
    check("a duplicate ISBN is refused", rc != 0, "rc=%s err=%s" % (rc, err))
    cli(project, "book", "add", "--title", "Z", "--author", "C", "--isbn", "I2",
        "--publication-year", "2002")
    rc, out, err = cli(project, "book", "search", "--term", "Z")
    check("search by title works", "Z" in out and "X" not in out, out)


def probe_12():
    project = fresh("12")
    for name, email in (("Alice", "alice@example.com"),
                        ("Bob", "bob@example.com"),
                        ("Carol", "carol@other.org")):
        cli(project, "customer", "add", "--name", name, "--email", email)
    example = cli(project, "customer", "list", "--email-domain", "example.com")[1]
    other = cli(project, "customer", "list", "--email-domain", "other.org")[1]
    check("email-domain filter keeps only the domain",
          example.count("Customer(") == 2 and other.count("Customer(") == 1,
          "example=%s other=%s" % (example[:80], other[:80]))
    check("search by name works",
          "Alice" in cli(project, "customer", "search", "--term", "Alice")[1])
    rc, out, err = cli(project, "customer", "add", "--name", "Dup",
                       "--email", "alice@example.com")
    check("the unique email is enforced", rc != 0, "rc=%s err=%s" % (rc, err))


def probe_13():
    project = fresh("13")
    cli(project, "product", "add", "--sku", "S1", "--name", "A", "--category",
        "tools", "--price", "10", "--stock-quantity", "5")
    rc, out, err = cli(project, "product", "add", "--sku", "S1", "--name", "B",
                       "--category", "tools", "--price", "20",
                       "--stock-quantity", "1")
    check("a duplicate SKU is refused", rc != 0, "rc=%s err=%s" % (rc, err))
    cli(project, "product", "add", "--sku", "S2", "--name", "C", "--category",
        "food", "--price", "30", "--stock-quantity", "50")
    check("category filter",
          cli(project, "product", "list", "--category", "tools")[1].count("Product(") == 1)
    check("low stock is reachable",
          cli(project, "product", "list", "--max-stock", "10")[1].count("Product(") == 1)


def probe_14():
    project = fresh("14")
    cli(project, "project", "add", "--name", "P", "--status", "active")
    cli(project, "project", "delete", "--id", "1")
    check("the deleted project is no longer listed",
          "P" not in cli(project, "project", "list")[1])
    rows = sql(project, "SELECT * FROM projects")
    check("the project ROW survives (soft delete)", len(rows) == 1, str(rows))


def probe_15():
    project = fresh("15")
    cli(project, "product", "add", "--name", "Zebra", "--price", "30",
        "--quantity", "3")
    cli(project, "product", "add", "--name", "Apple", "--price", "10",
        "--quantity", "1")
    asc = cli(project, "product", "list", "--sort-by", "price", "--order", "asc")[1]
    desc = cli(project, "product", "list", "--sort-by", "price",
               "--order", "desc")[1]
    check("ascending order starts at the cheapest, descending at the dearest",
          asc.find("Apple") < asc.find("Zebra")
          and desc.find("Zebra") < desc.find("Apple"),
          "asc=%s desc=%s" % (asc[:60], desc[:60]))


def probe_16():
    project = fresh("16")
    for index in range(5):
        cli(project, "customer", "add", "--first-name", "N%d" % index,
            "--last-name", "L", "--email", "n%d@x" % index)
    page1 = cli(project, "customer", "list", "--page-size", "2")[1]
    page2 = cli(project, "customer", "list", "--page-size", "2", "--page", "2")[1]
    check("page 1 and page 2 return different items",
          page1 != page2 and "N0" in page1 and "N2" in page2,
          "p1=%s p2=%s" % (page1[:50], page2[:50]))
    check("total and total_pages are reported",
          "'total': 5" in page1 and "'total_pages': 3" in page1, page1[:200])


def probe_17():
    """The four filters the specification asks for, and their combination.

    "Users must be able to search by name, filter by category, specify a
    maximum price and specify a minimum quantity. All filters must be
    combinable."

    The specification asks for NO creation command: searching and filtering
    is the whole application, so the rows the filters must find are seeded
    straight into its database rather than invented through a command the
    prompt never requested.
    """
    project = fresh("17")
    cli(project, "product", "list")          # let the app create its schema
    columns = [
        row[1] for row in sql(project, "PRAGMA table_info(products)")
        if len(row) >= 6 and not row[5]
    ]
    if not columns:
        check("the products table exists", False, "no columns")
        return
    check("the products table exists", True)

    def seed(name, category, price, quantity):
        data = {
            column: (
                name if "name" in column
                else category if "categor" in column
                else price if "price" in column
                else quantity if "quant" in column or "stock" in column
                else "x"
            )
            for column in columns
        }
        names = ", ".join(data)
        values = ", ".join(repr(value) for value in data.values())
        error = execute(
            project, "INSERT INTO products (%s) VALUES (%s)" % (names, values)
        )
        if error:
            check("the probe can seed a row", False, error)
        return error

    seed("Widget", "tools", 10, 5)
    seed("Bread", "food", 20, 1)
    stored = sql(project, "SELECT name FROM products")
    if len(stored) != 2:
        check("the probe seeded two rows", False, "%r" % (stored,))
        return
    check("the probe seeded two rows", True)

    def listed(*args):
        rc, out, err = cli(project, "product", "list", *args)
        return out or err

    by_category = listed("--category", "tools")
    check("filter by category keeps only that category",
          contains(by_category, "Widget") and not contains(by_category, "Bread"),
          by_category)

    by_price = listed("--max-price", "15")
    check("a maximum price excludes the dearer row",
          contains(by_price, "Widget") and not contains(by_price, "Bread"),
          by_price)

    by_quantity = listed("--min-quantity", "3")
    check("a minimum quantity excludes the scarcer row",
          contains(by_quantity, "Widget") and not contains(by_quantity, "Bread"),
          by_quantity)

    combined = listed("--category", "tools", "--max-price", "15",
                      "--min-quantity", "3")
    check("the filters combine",
          contains(combined, "Widget") and not contains(combined, "Bread"),
          combined)

    rc, out, err = cli(project, "product", "search", "--term", "Widget")
    found = out or err
    check("search by name finds the row and not the other",
          rc == 0 and contains(found, "Widget") and not contains(found, "Bread"),
          found)


def probe_18():
    project = fresh("18")
    cli(project, "contact", "add", "--first-name", "Alice", "--last-name", "A",
        "--email", "a@x.com")
    export = project / "exported.csv"
    rc, out, err = cli(project, "contact", "export", "--filename",
                       str(export.resolve()))
    check("export writes a CSV", rc == 0 and export.exists(), "rc=%s err=%s" % (rc, err))
    # The exported header defines the format, so the incoming file is built
    # from it rather than guessed — with the id left EMPTY, since the point is
    # to add a row, not to re-import the one already stored.
    lines = export.read_text().splitlines() if export.exists() else []
    header = lines[0] if lines else "id,first_name,last_name,email"
    columns = header.split(",")

    def csv_row(values):
        return ",".join(values.get(column, "") for column in columns)

    incoming = project / "incoming.csv"
    incoming.write_text("%s\n%s\n%s\n" % (
        header,
        csv_row({"first_name": "Bob", "last_name": "B", "email": "b@x.com"}),
        csv_row({}),
    ))
    rc, out, err = cli(project, "contact", "import", "--filename",
                       str(incoming.resolve()))
    rows = sql(project, "SELECT * FROM contacts")
    check("the valid row is imported and the invalid one rejected",
          any("b@x.com" in str(row) for row in rows) and len(rows) == 2,
          "rc=%s out=%s err=%s rows=%s" % (rc, out[:80], err[:80], rows))
    check("the rejection is reported to the caller",
          contains(out + err, "not imported") or contains(out + err, "error"),
          "rc=%s out=%s err=%s" % (rc, out[:120], err[:120]))
    check("the existing contact is untouched",
          any("a@x.com" in str(row) for row in rows), str(rows))


def probe_19():
    project = fresh("19")
    cli(project, "task", "add", "--title", "T1", "--description", "D")
    exported = project / "tasks.json"
    rc, out, err = cli(project, "task", "export", "--filename",
                       str(exported.resolve()))
    content = exported.read_text() if exported.exists() else ""
    check("JSON export writes the task", rc == 0 and "T1" in content,
          "rc=%s err=%s content=%s" % (rc, err[:80], content[:80]))
    cli(project, "task", "delete", "--id", "1")
    rc, out, err = cli(project, "task", "import", "--filename",
                       str(exported.resolve()))
    check("import restores what export wrote",
          "T1" in cli(project, "task", "list")[1],
          "rc=%s err=%s" % (rc, err[:100]))
    bad = project / "bad.json"
    bad.write_text('[{"unexpected": true}]')
    before = cli(project, "task", "list")[1]
    rc, out, err = cli(project, "task", "import", "--filename", str(bad.resolve()))
    after = cli(project, "task", "list")[1]
    reported = contains(out + err, "not imported") or contains(out + err, "error")
    check("an invalid file is rejected without touching the database",
          before == after and (rc != 0 or reported),
          "rc=%s out=%s err=%s" % (rc, out[:100], err[:100]))


def probe_20():
    project = fresh("20")
    add_row(project, "product", name="P1", price="10")
    add_row(project, "product", name="P2", price="20")
    add_row(project, "sale", product_id=1, quantity="2", total_amount="20")
    add_row(project, "sale", product_id=1, quantity="3", total_amount="30")
    # The specification asks for ONE report over every product ("total sales
    # amount and number of sales per product"), so it is run with no id at
    # all — and it must not ask for one.
    rc, out, err = cli(project, "sale", "report")
    check("the report carries BOTH the amount and the number of sales",
          rc == 0 and "50" in out and "count" in out.lower(),
          "rc=%s out=%s err=%s" % (rc, out[:200], err[:120]))
    check("the report demands no id the spec never mentions",
          rc == 0 and "--id" not in cli(project, "sale", "report", "--help")[1],
          "rc=%s err=%s" % (rc, err[:120]))


def probe_21():
    project = fresh("21")
    add_row(project, "customer", email="c1@x")
    add_row(project, "customer", email="c2@x", first_name="G", last_name="G")
    add_row(project, "order", customer_id=1, order_date="2026-01-01",
            status="pending")
    add_row(project, "order", customer_id=2, order_date="2026-01-02",
            status="pending")
    rc, out, err = cli(project, "order", "list", "--customer-id", "1")
    check("order list filters by customer",
          out.count("Order(") == 1,
          "rc=%s out=%s err=%s" % (rc, out[:200], err[:120]))


def inserted_line(project, line_table, quantity=3, price=10):
    """Insert one order/invoice line, filling every NOT NULL column.

    The delivered schema is the generator's, so the values are chosen by the
    COLUMN's own name rather than assumed: a missing NOT NULL column would fail
    the insert and hide what the probe is actually measuring.
    """
    info = sql(project, "PRAGMA table_info(%s)" % line_table)
    values = {}
    for row in info:
        column, notnull, default, primary = row[1], row[3], row[4], row[5]
        if primary:
            continue
        # A recognised column is always written, even when the schema gives it
        # a default: orderitems.quantity defaults to 1 and unit_price to 0.0, so
        # leaving them out would make the report sum zero.
        if "quant" in column:
            values[column] = quantity
        elif "price" in column:
            values[column] = price
        elif "total" in column:
            values[column] = quantity * price
        elif column.endswith("_id"):
            values[column] = 1
        elif notnull and default is None:
            values[column] = "x"
    if not values:
        return
    keys = ",".join(values)
    marks = ",".join("?" * len(values))
    for db in project.glob("*.db"):
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO %s (%s) VALUES (%s)" % (line_table, keys, marks),
                     tuple(values.values()))
        conn.commit()
        conn.close()


def probe_22():
    project = fresh("22")
    add_row(project, "customer", email="c@x")
    add_row(project, "product")
    add_row(project, "order")
    lines = sql(project, "SELECT name FROM sqlite_master WHERE type='table'")
    line_table = next((str(row[0]) for row in lines
                       if "item" in str(row[0]) or "line" in str(row[0])), None)
    if line_table:
        inserted_line(project, line_table)
        rc, out, err = cli(project, "order", "report", "--id", "1")
        check("the order total is computed from its lines",
              "30" in out, "rc=%s out=%s err=%s" % (rc, out[:200], err[:120]))
    else:
        check("an order-lines table exists", False, str(lines))


def probe_23():
    project = fresh("23")
    cli(project, "post", "add", "--title", "T", "--content", "C")
    cli(project, "tag", "add", "--name", "python")
    rc, out, err = cli(project, "post", "detail", "--id", "1")
    check("post detail runs (no SQL error)", rc == 0,
          "rc=%s out=%s err=%s" % (rc, out[:120], err[:200]))


def probe_24():
    project = fresh("24")
    add_row(project, "project", name="P1")
    add_row(project, "project", name="P2")
    add_row(project, "task", title="T1", project_id=1)
    add_row(project, "task", title="T2", project_id=2)
    rc, out, err = cli(project, "task", "list", "--project-id", "1")
    check("task list filters by project", out.count("Task(") == 1,
          "rc=%s out=%s err=%s" % (rc, out[:150], err[:100]))


def probe_25():
    project = fresh("25")
    add_row(project, "department", name="D1")
    add_row(project, "department", name="D2")
    add_row(project, "employee", first_name="E", last_name="One",
            department_id=1, email="e1@x.com")
    add_row(project, "employee", first_name="F", last_name="Two",
            department_id=2, email="e2@x.com")
    rc, out, err = cli(project, "employee", "list", "--department-id", "1")
    check("employee list filters by department", out.count("Employee(") == 1,
          "rc=%s out=%s err=%s" % (rc, out[:150], err[:100]))


def loan_of(project):
    """(add-command args, active flag, close command) read from the surface."""
    return None


def probe_26():
    project = fresh("26")
    add_row(project, "book", title="B", isbn="1")
    add_row(project, "member", first_name="M", last_name="One", email="m@x")
    loan = {"book_id": 1, "member_id": 1, "due_date": "2026-02-01"}
    first = add_row(project, "loan", **loan)
    second = add_row(project, "loan", **loan)
    check("a second active loan on the same book is refused",
          first[0] == 0 and second[0] != 0,
          "first=%s second=%s" % (first[:2], second[:2]))


def probe_27():
    project = fresh("27")
    add_row(project, "customer", email="c@x")
    # The two rooms need distinct room numbers, or the second insert is
    # refused and the "other room" case never runs.
    add_row(project, "room", room_number="101", capacity="2", floor="1")
    add_row(project, "room", room_number="102", capacity="2", floor="1")

    def reserve(room, start, end):
        return add_row(project, "reservation", customer_id=1, room_id=room,
                       start_date=start, end_date=end)

    made = reserve(1, "2026-01-01", "2026-01-05")
    overlapping = reserve(1, "2026-01-03", "2026-01-07")
    adjacent = reserve(1, "2026-01-05", "2026-01-08")
    other_room = reserve(2, "2026-01-03", "2026-01-07")
    check("overlapping is refused", made[0] == 0 and overlapping[0] != 0,
          "made=%s overlap=%s" % (made[:2], overlapping[:2]))
    check("adjacent and other-room are allowed",
          adjacent[0] == 0 and other_room[0] == 0,
          "adjacent=%s other=%s" % (adjacent[:2], other_room[:2]))


def probe_28():
    project = fresh("28")
    cli(project, "customer", "add", "--name", "C", "--email", "c@x")
    cli(project, "invoice", "add", "--customer-id", "1")
    check("the total is not an input of invoice add",
          "--total-amount" not in cli(project, "invoice", "add", "--help")[1])
    lines = sql(project, "SELECT name FROM sqlite_master WHERE type='table'")
    line_table = next((str(row[0]) for row in lines
                       if "item" in str(row[0]) or "line" in str(row[0])), None)
    if line_table:
        inserted_line(project, line_table, quantity=3, price=7)
    rc, out, err = cli(project, "invoice", "calculate-total", "--id", "1")
    check("the invoice total is computed from its lines", "21" in out,
          "rc=%s out=%s err=%s" % (rc, out[:200], err[:150]))


def probe_29():
    project = fresh("29")
    names = {path.stem for path in project.glob("*.py")}
    check("models/repository/service/cli are separate modules",
          {"models"} <= names and len(names) >= 4, str(sorted(names)))
    cli_text = (project / "cli.py").read_text() if (project / "cli.py").exists() else ""
    check("the CLI does not reach SQLite itself", "import sqlite3" not in cli_text)


def probe_30():
    project = fresh("30")
    sources = "\n".join(path.read_text() for path in project.glob("*.py"))
    check("the repository contract is an abstraction (ABC/Protocol)",
          "ABC" in sources or "Protocol" in sources)
    cli_text = (project / "cli.py").read_text() if (project / "cli.py").exists() else ""
    check("the CLI does not reach SQLite itself", "import sqlite3" not in cli_text)


def probe_31():
    project = fresh("31")
    add_row(project, "customer", email="c@x")
    add_row(project, "account", customer_id=1, account_type="savings",
            balance="100")
    cli(project, "account", "deposit", "--id", "1", "--amount", "50")
    balance = sql(project, "SELECT balance FROM accounts")
    overdraft = cli(project, "account", "withdraw", "--id", "1", "--amount", "500")
    after = sql(project, "SELECT balance FROM accounts")
    check("a deposit moves the balance", "150" in str(balance), str(balance))
    check("an overdraft is refused and changes nothing",
          overdraft[0] != 0 and after == balance,
          "rc=%s err=%s after=%s" % (overdraft[0], overdraft[2][:80], after))


def probe_32():
    project = fresh("32")
    add_row(project, "customer", email="c@x")
    add_row(project, "order", customer_id=1, total_amount="10",
            status="pending")
    shipped = cli(project, "order", "ship", "--id", "1")
    cancelled = cli(project, "order", "cancel", "--id", "1")
    check("a shipped order cannot be cancelled",
          shipped[0] == 0 and cancelled[0] != 0,
          "ship=%s cancel=%s err=%s" % (shipped[:2], cancelled[:2], cancelled[2][:80]))
    add_row(project, "order", customer_id=1, total_amount="11",
            status="pending")
    cli(project, "order", "cancel", "--id", "2")
    back = cli(project, "order", "ship", "--id", "2")
    check("a cancelled order cannot be shipped", back[0] != 0,
          "rc=%s err=%s" % (back[0], back[2][:80]))


def probe_33():
    project = fresh("33")
    help_text = surface(project)
    groups = re.findall(r"^  (\w[\w-]*)\s+", help_text, re.M)
    if not groups:
        check("the application exposes a data command", False, help_text[:100])
        return
    # The first group may be the audit record itself, which has no ``add``:
    # pick the first group that actually offers one.
    group = next(
        (candidate for candidate in groups
         if "audit" not in candidate.lower()
         and "add" in cli(project, candidate, "--help")[1]),
        groups[0],
    )
    created = add_row(project, group)
    tables = [str(row[0]) for row in
              sql(project, "SELECT name FROM sqlite_master WHERE type='table'")]
    audit_tables = [name for name in tables if "audit" in name.lower()]
    entries = sum(len(sql(project, "SELECT * FROM %s" % name))
                  for name in audit_tables)
    check("creating a row records an audit entry",
          created[0] == 0 and entries >= 1,
          "group=%s rc=%s err=%s tables=%s" % (group, created[0],
                                               created[2][:80], tables))


def probe_34():
    project = fresh("34")
    rc, out, err = cli(project, "order", "add", "--customer-id", "1")
    check("a missing customer is a clean error, not a crash",
          rc != 0 and "Traceback" not in err and
          ("foreign key" in err.lower() or "customer" in err.lower()),
          "rc=%s err=%s" % (rc, err[:150]))


def probe_35():
    project = fresh("35")
    add_row(project, "product", name="A", price="10")
    bulk = cli(project, "product", "bulk-update", "--ids", "1",
               "--stock-quantity", "9")
    check("a bulk update can change only the quantity",
          bulk[0] == 0, "rc=%s err=%s" % (bulk[0], bulk[2][:120]))


def probe_36():
    project = fresh("36")
    cli(project, "category", "add", "--name", "Electronics")
    cli(project, "category", "add", "--name", "Empty")
    cli(project, "product", "add", "--name", "TV", "--price", "100",
        "--category-id", "1")
    refused = cli(project, "category", "delete", "--id", "1")
    allowed = cli(project, "category", "delete", "--id", "2")
    check("a referenced category cannot be deleted",
          refused[0] != 0 and allowed[0] == 0,
          "refused=%s allowed=%s err=%s" % (refused[:2], allowed[:2], refused[2][:100]))
    check("the category survives the refusal",
          any("Electronics" in str(row) for row in
              sql(project, "SELECT * FROM categories")))


def probe_37():
    project = fresh("37")
    cli(project, "project", "add", "--name", "P")
    cli(project, "task", "add", "--title", "T1", "--project-id", "1")
    cli(project, "task", "add", "--title", "T2", "--project-id", "1")
    rc, out, err = cli(project, "project", "delete", "--id", "1")
    tasks = sql(project, "SELECT * FROM tasks")
    check("deleting a project cascades to its tasks",
          rc == 0 and tasks == [], "rc=%s tasks=%s err=%s" % (rc, tasks, err[:100]))


def probe_38():
    project = fresh("38")
    for email in ("a@x.com", "b@x.com"):
        cli(project, "user", "add", "--email", email, "--password-hash", "h")
    conn = sqlite3.connect(project / "app.db")
    conn.execute(
        "INSERT INTO documents (title, content, user_id, is_public,"
        " created_at, updated_at) VALUES ('secret','c',2,0,'2026-01-01','2026-01-01')"
    )
    conn.commit()
    conn.close()
    hidden = cli(project, "document", "list", "--user-id", "1")
    denied = cli(project, "document", "delete", "--id", "1", "--user-id", "1")
    check("another user's document is not listed", "secret" not in hidden[1],
          hidden[1][:100])
    check("another user's document cannot be deleted",
          denied[0] != 0 and len(sql(project, "SELECT * FROM documents")) == 1,
          "rc=%s err=%s" % (denied[0], denied[2][:100]))


def probe_39():
    project = fresh("39")
    cli(project, "product", "list")          # creates the schema
    for db in project.glob("*.db"):
        conn = sqlite3.connect(db)
        conn.execute("INSERT INTO users (email, password_hash, is_active, role)"
                     " VALUES ('admin@x','h',1,'admin'), ('user@x','h',1,'user')")
        conn.commit()
        conn.close()
    refused = cli(project, "product", "add", "--actor-id", "2", "--name", "X",
                  "--price", "1")
    allowed = cli(project, "product", "add", "--actor-id", "1", "--name", "Y",
                  "--price", "1")
    own = cli(project, "user", "update", "--actor-id", "2", "--id", "2",
              "--email", "u2@x")
    other = cli(project, "user", "update", "--actor-id", "2", "--id", "1",
                "--email", "stolen@x")
    check("a normal user cannot manage products", refused[0] != 0, refused[2][:90])
    check("an administrator can manage products", allowed[0] == 0, allowed[2][:90])
    check("a user may edit its own account but not another's",
          own[0] == 0 and other[0] != 0,
          "own=%s other=%s" % (own[:2], other[:2]))


def probe_40():
    project = fresh("40")
    cli(project, "order", "list")             # creates the schema
    order_help = cli(project, "order", "--help")[1]
    check("the application can create the order it confirms",
          "add" in order_help,
          "commands=%s" % " ".join(order_help.split())[:120])
    # The delivered CLI offers no way to create an order, so the row the
    # confirmation needs is written directly: the point here is the
    # notification, not the creation.
    for db in project.glob("*.db"):
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("INSERT INTO orders (customer_id, total_amount)"
                     " VALUES (1, 10)")
        conn.commit()
        conn.close()
    rc, out, err = cli(project, "order", "confirm", "--id", "1")
    check("confirming an order logs a notification",
          "notif" in (out + err).lower(),
          "rc=%s out=%s err=%s" % (rc, out[:80], err[:120]))


PROBES = {
    "%02d" % number: globals()["probe_%02d" % number]
    for number in range(1, 41)
    if "probe_%02d" % number in globals()
}


def main():
    wanted = sys.argv[1:] or sorted(PROBES)
    verdicts = {}
    for number in wanted:
        probe = PROBES.get(number)
        if probe is None:
            continue
        del RESULTS[:]
        print("== %s ==" % number)
        try:
            probe()
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            check("the probe itself failed", False, repr(exc))
        passed = sum(1 for ok in RESULTS if ok)
        verdicts[number] = (passed, len(RESULTS))
    print()
    print("verdicts: %s" % {k: "%d/%d" % v for k, v in sorted(verdicts.items())})
    total_pass = sum(p for p, _ in verdicts.values())
    total = sum(t for _, t in verdicts.values())
    print("TOTAL %d/%d checks" % (total_pass, total))


if __name__ == "__main__":
    main()
