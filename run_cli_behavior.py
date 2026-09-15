#!/usr/bin/env python3
"""End-to-end behavioural gate on the GENERATED CLIs (no LLM).

`run_facade_execution.py` proves each enumerated command is REACHABLE and exits
0 on a mapped intention. This runner proves the paths that mapping cannot
express: a value the specification DECLARES must be enforced, a command it
never asked for must be absent, and the stateful workflows must actually move
the state the specification describes (borrow decrements, return restores).

Every assertion is executed against the shipped CLI on a FRESH database, so a
generator regression shows up here as a non-zero exit or a wrong row.

Usage:
    python3 run_cli_behavior.py                    # every covered project
    python3 run_cli_behavior.py --prompt expenses
"""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from pathlib import Path

GENERATED_ROOT = Path("generated")


class Suite:
    """A CLI/DB assertion suite with a pass/fail tally."""

    def __init__(self, ident: str) -> None:
        self.ident = ident
        self.project = (GENERATED_ROOT / ident).resolve()
        self.fails: list[str] = []
        self.n_ok = 0
        self.db: Path | None = None

    # -- assertions ---------------------------------------------------------
    def check(self, label: str, cond, detail: str = "") -> None:
        if cond:
            self.n_ok += 1
            print("OK    %s" % label)
        else:
            self.fails.append("%s %s" % (label, detail))
            print("FAIL  %s %s" % (label, detail))

    def run(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable] + args, cwd=str(self.project),
            capture_output=True, text=True, timeout=60,
        )

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return self.run(["cli.py", *args])

    # -- database -----------------------------------------------------------
    def bootstrap(self) -> None:
        """Delete every DB and let the CLI recreate the schema."""
        for stale in self.project.glob("*.db"):
            stale.unlink()
        first = self.cli("--help")
        self.check("cli.py --help exits 0", first.returncode == 0,
                   first.stderr[-200:])
        cands = sorted(self.project.glob("*.db"))
        # Some CLIs create the DB lazily: an explicit command is run next by
        # the caller, then `db` is resolved once the file exists.
        self.db = cands[0] if cands else None

    def resolve_db(self) -> None:
        if self.db is not None and self.db.exists():
            return
        cands = sorted(self.project.glob("*.db"))
        self.db = cands[0] if cands else None
        self.check("a sqlite database was created", self.db is not None,
                   str(cands))

    def one(self, query: str, params=()):
        con = sqlite3.connect(str(self.db))
        try:
            return con.execute(query, params).fetchone()
        finally:
            con.close()

    def write(self, query: str, params=()) -> None:
        con = sqlite3.connect(str(self.db))
        try:
            con.execute(query, params)
            con.commit()
        finally:
            con.close()

    # -- reporting ----------------------------------------------------------
    def report(self) -> bool:
        ok = not self.fails
        print("\n%s: %s  (%d ok, %d fail)"
              % (self.ident.upper(), "PASS" if ok else "FAIL",
                 self.n_ok, len(self.fails)))
        for f in self.fails:
            print("  - %s" % f)
        return ok
# ---------------------------------------------------------------------------
# expenses — the specification's own value vocabulary, flag and defaults
# ---------------------------------------------------------------------------

def suite_expenses() -> Suite:
    s = Suite("expenses")
    s.bootstrap()

    # 1. `expense add` WITHOUT the optional --expense-date must not crash.
    r = s.cli("expense", "category", "add", "--name", "food",
              "--description", "food and drink", "--budget", "100")
    s.check("category add exits 0", r.returncode == 0, r.stderr[-300:])
    s.resolve_db()
    r = s.cli("expense", "add", "--amount", "12.50", "--description", "lunch",
              "--category", "1")
    s.check("expense add without --expense-date exits 0",
            r.returncode == 0, "rc=%s err=%s" % (r.returncode, r.stderr[-300:]))
    rows = s.one("SELECT amount_cents, expense_date, payment_method, "
                 "is_recurring FROM expenses")
    s.check("one expense stored", rows is not None, repr(rows))
    if rows:
        import datetime
        cents, edate, method, rec = rows
        s.check("amount 12.50 -> 1250 cents", cents == 1250, repr(cents))
        s.check("expense_date defaults to today",
                str(edate) == datetime.date.today().isoformat(), repr(edate))
        s.check("payment_method default applied", method == "cash", repr(method))
        s.check("is_recurring default applied", rec in (0, False), repr(rec))

    # 2. The flag the specification names, and no synthesized twin.
    r = s.cli("expense", "add", "--amount", "5", "--description", "coffee",
              "--category", "1", "--recurring")
    s.check("--recurring accepted", r.returncode == 0,
            "rc=%s err=%s" % (r.returncode, r.stderr[-300:]))
    rec = s.one("SELECT is_recurring FROM expenses ORDER BY id DESC LIMIT 1")
    s.check("--recurring stored True", bool(rec) and rec[0] in (1, True),
            repr(rec))
    r = s.cli("expense", "add", "--amount", "5", "--description", "x",
              "--category", "1", "--no-recurring")
    s.check("--no-recurring absent (exit 2)", r.returncode == 2,
            "rc=%s" % r.returncode)

    # 3. The declared value vocabulary is ENFORCED.
    r = s.cli("expense", "add", "--amount", "5", "--description", "x",
              "--category", "1", "--method", "bitcoin")
    s.check("--method outside the declared set rejected (exit 2)",
            r.returncode == 2, "rc=%s" % r.returncode)
    r = s.cli("expense", "add", "--amount", "5", "--description", "x",
              "--category", "1", "--method", "card")
    s.check("--method inside the declared set accepted", r.returncode == 0,
            "rc=%s err=%s" % (r.returncode, r.stderr[-300:]))

    # 4. Every command the specification enumerates exists ...
    for path in (["expense", "report", "monthly"], ["expense", "report", "yearly"],
                 ["expense", "recurring", "detect"], ["expense", "export"],
                 ["expense", "list"], ["budget", "add"], ["budget", "list"],
                 ["budget", "update"], ["budget", "delete"],
                 ["expense", "category", "add"], ["expense", "category", "list"],
                 ["expense", "category", "update"],
                 ["expense", "category", "delete"]):
        r = s.cli(*path, "--help")
        s.check("command exists: %s" % " ".join(path), r.returncode == 0,
                "rc=%s" % r.returncode)

    # 4bis. A report's money values are DISPLAYED as decimals while the
    # database keeps integer cents. The specification's convention is
    # two-sided, and both halves are asserted here: the console (path 1) and
    # the stored column (path 2). 1250 + 500 + 500 cents were inserted above.
    from datetime import date as _date
    month = _date.today().strftime("%Y-%m")
    year = _date.today().strftime("%Y")
    r = s.cli("expense", "report", "monthly", "--month", month)
    s.check("expense report monthly exits 0", r.returncode == 0,
            "rc=%s err=%s" % (r.returncode, r.stderr[-300:]))
    s.check("report prints the total as a decimal", "'total': 22.50" in r.stdout,
            r.stdout.strip())
    s.check("report prints per_category as decimals",
            "'per_category': {1: 22.50}" in r.stdout, r.stdout.strip())
    s.check("report does not print raw cents", "2250" not in r.stdout,
            r.stdout.strip())
    s.check("SQL keeps the period total in cents",
            s.one("SELECT SUM(amount_cents) FROM expenses "
                  "WHERE expense_date >= ? AND expense_date <= ?",
                  (month + "-01", month + "-31"))[0] == 2250, "")
    r = s.cli("expense", "report", "yearly", "--year", year)
    s.check("expense report yearly exits 0", r.returncode == 0,
            "rc=%s err=%s" % (r.returncode, r.stderr[-300:]))
    s.check("yearly prints average_monthly_spend as a decimal",
            "'average_monthly_spend': 22.50" in r.stdout, r.stdout.strip())

    # 5. ... and nothing it never asked for is exposed.
    for path in (["expense", "update"], ["expense", "delete"],
                 ["expense", "get"], ["expense", "detect"], ["budget", "check"],
                 ["category", "detect"], ["category", "check"],
                 ["category", "add"], ["category", "list"]):
        r = s.cli(*path, "--help")
        s.check("absent: %s" % " ".join(path), r.returncode == 2,
                "rc=%s" % r.returncode)
    return s
# ---------------------------------------------------------------------------
# library_system — the stateful borrow/return workflow
# ---------------------------------------------------------------------------

def suite_library_system() -> Suite:
    s = Suite("library_system")
    s.bootstrap()

    # The specification exposes no `author add`, and `book add --author-id`
    # needs one: seed the parent row directly, then drive everything else
    # through the CLI.
    r = s.cli("library", "overdue")
    s.check("library overdue exits 0 (bootstraps the DB)", r.returncode == 0,
            r.stderr[-300:])
    s.resolve_db()
    s.write("INSERT INTO authors (name, birth_year, biography) VALUES (?,?,?)",
            ("Ada", 1815, "pioneer"))
    s.check("author seeded", s.one("SELECT id FROM authors") is not None)

    # 1. `library book add` with the specification's own option names.
    r = s.cli("library", "book", "add", "--title", "Dune", "--isbn", "111",
              "--author-id", "1", "--published-year", "1965", "--copies", "1")
    s.check("book add exits 0", r.returncode == 0, r.stderr[-300:])
    row = s.one("SELECT available_copies FROM books WHERE isbn='111'")
    s.check("--copies stored as available_copies", row and row[0] == 1,
            repr(row))
    r = s.cli("library", "book", "add", "--title", "x", "--isbn", "y",
              "--author-id", "1", "--published-year", "2000",
              "--available-copies", "3")
    s.check("--available-copies absent (exit 2)", r.returncode == 2,
            "rc=%s" % r.returncode)

    # 2. The spec's list/search options, and only those.
    r = s.cli("library", "book", "list", "--available-only")
    s.check("book list --available-only exits 0", r.returncode == 0,
            r.stderr[-200:])
    r = s.cli("library", "book", "list", "--author", "Ada")
    s.check("book list --author exits 0", r.returncode == 0, r.stderr[-200:])
    r = s.cli("library", "book", "search", "--query", "Dune")
    s.check("book search --query exits 0", r.returncode == 0, r.stderr[-200:])
    s.check("book search --query finds it", "Dune" in r.stdout, r.stdout[-200:])
    r = s.cli("library", "book", "search", "--term", "Dune")
    s.check("book search --term absent (exit 2)", r.returncode == 2,
            "rc=%s" % r.returncode)

    # 3. member add/list.
    r = s.cli("library", "member", "add", "--name", "Bob",
              "--email", "bob@example.com")
    s.check("member add exits 0", r.returncode == 0, r.stderr[-300:])
    r = s.cli("library", "member", "list", "--active-only")
    s.check("member list --active-only exits 0", r.returncode == 0,
            r.stderr[-200:])

    # 4. borrow: decrements, creates an active loan, refuses when none left.
    r = s.cli("library", "borrow", "--member-id", "1", "--book-id", "1")
    s.check("borrow exits 0", r.returncode == 0, r.stderr[-300:])
    row = s.one("SELECT available_copies FROM books WHERE id=1")
    s.check("borrow decrements available_copies to 0", row and row[0] == 0,
            repr(row))
    loan = s.one("SELECT id, status FROM loans WHERE book_id=1 AND member_id=1")
    s.check("loan row created (active)", loan and loan[1] == "active",
            repr(loan))
    r = s.cli("library", "borrow", "--member-id", "1", "--book-id", "1")
    s.check("second borrow of the same book refused", r.returncode != 0,
            "rc=%s" % r.returncode)

    # 5. A DIFFERENT book by the SAME member works.
    r = s.cli("library", "book", "add", "--title", "Emma", "--isbn", "222",
              "--author-id", "1", "--published-year", "1815", "--copies", "1")
    s.check("second book add exits 0", r.returncode == 0, r.stderr[-300:])
    r = s.cli("library", "borrow", "--member-id", "1", "--book-id", "2")
    s.check("same member borrows a DIFFERENT book", r.returncode == 0,
            r.stderr[-300:])

    # 6. member history covers both loans; overdue runs.
    r = s.cli("library", "member", "history", "--member-id", "1")
    s.check("member history exits 0", r.returncode == 0, r.stderr[-300:])
    s.check("history covers both loans",
            "book_id=1" in r.stdout and "book_id=2" in r.stdout, r.stdout[-300:])
    r = s.cli("library", "overdue")
    s.check("overdue exits 0", r.returncode == 0, r.stderr[-300:])

    # 7. return: restores the copy, stamps the date and the status.
    loan_id = loan[0] if loan else 1
    r = s.cli("library", "return", "--loan-id", str(loan_id))
    s.check("return exits 0", r.returncode == 0, r.stderr[-300:])
    row = s.one("SELECT available_copies FROM books WHERE id=1")
    s.check("return restores available_copies to 1", row and row[0] == 1,
            repr(row))
    lr = s.one("SELECT return_date, status FROM loans WHERE id=?", (loan_id,))
    s.check("return_date stamped", lr and lr[0], repr(lr))
    s.check("status returned", lr and lr[1] in ("returned", "RETURNED"),
            repr(lr))

    # 8. Nothing the specification never asked for is exposed — including the
    #    dead `member borrow --id N` command (S14).
    for path in (["library", "loan", "add"], ["library", "loan", "list"],
                 ["library", "loan", "report"], ["library", "loan", "cancel"],
                 ["library", "member", "borrow"], ["library", "member", "update"],
                 ["library", "member", "delete"], ["library", "book", "update"],
                 ["library", "book", "delete"], ["library", "author", "list"],
                 ["library", "author", "add"], ["library", "member", "renew"]):
        r = s.cli(*path, "--help")
        s.check("absent: %s" % " ".join(path), r.returncode == 2,
                "rc=%s" % r.returncode)
    return s


# ---------------------------------------------------------------------------
# Static generator-output assertions (no CLI, no database)
#
# The suites above drive the SHIPPED CLI. These read the SHIPPED SOURCES for
# the three defects a fill can hide inside a method the other gates never
# call: a value the caller supplies but the body drops, a query built and then
# overwritten, and a date parameter the body re-formats. The generator's own
# verifier (`agentlib.generation.repo_render._repo_fidelity_violations`) is
# reused here, so the shipped tree must satisfy exactly the rule the fill was
# held to — the gate cannot drift from the rule.
# ---------------------------------------------------------------------------

def suite_source_fidelity() -> Suite:
    import ast
    import re as _re
    from agentlib.generation.repo_render import _repo_fidelity_violations

    s = Suite("source-fidelity")

    for ident in ("expenses", "library_system"):
        project = (GENERATED_ROOT / ident).resolve()
        if not project.is_dir():
            continue
        # 1. Repository bodies: the fill rule, applied to what was SHIPPED.
        for repo in sorted(project.glob("*_repository.py")):
            tree = ast.parse(repo.read_text())
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef):
                    continue
                viol = _repo_fidelity_violations(node)
                s.check(
                    "%s: %s.%s is faithful" % (ident, repo.name, node.name),
                    not viol, "; ".join(viol)[:160],
                )
        # 2. Model annotations name the CLASS, never the module.
        models = project / "models.py"
        if models.exists():
            src = models.read_text()
            s.check(
                "%s: no annotation names the datetime MODULE" % ident,
                not _re.search(r":\s*(Optional\[)?datetime(\]|\s*=|,|\)|$)",
                               src, _re.M),
                "",
            )
    return s


# ---------------------------------------------------------------------------
# The fidelity RULE itself, on synthetic bodies (no LLM, no project)
#
# `source-fidelity` proves the SHIPPED bodies satisfy the rule. These cases
# prove the rule still REJECTS the shapes it exists for and still ACCEPTS the
# legitimate shapes around them — a rule that silently stopped firing would
# pass the shipped-source suite on a lucky tree. Three defective shapes (the
# overwritten query, `.isoformat()` on a parameter, a parameter never read)
# and four legitimate ones (incremental build, `+=` build, `.isoformat()` on a
# LOCAL datetime, the sentinel-in-loop idiom).
# ---------------------------------------------------------------------------

FIDELITY_CASES = [
    ("""def list_authors_with_books(self, include_inactive):
    with self.db.connect() as conn:
        query = 'SELECT a.* FROM authors a LEFT JOIN books b ON a.id = b.author_id'
        params = []
        if not include_inactive:
            query += ' AND a.id IN (SELECT author_id FROM books)'
        query = 'SELECT a.* FROM authors a INNER JOIN books b ON a.id = b.author_id'
        if not include_inactive:
            pass
        cur = conn.execute(query)
        return [dict(r) for r in cur.fetchall()]
""", True),
    ("""def export_to_csv(self, file_path, start_date, end_date):
    with self.db.connect() as conn:
        rows = conn.execute(
            'SELECT * FROM expenses WHERE expense_date BETWEEN ? AND ?',
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
        return [dict(r) for r in rows]
""", True),
    ("""def list_expenses(self, category_id, start_date):
    with self.db.connect() as conn:
        row = conn.execute('SELECT * FROM expenses').fetchall()
        return [dict(r) for r in row]
""", True),
    ("""def list_expenses(self, category_id, start_date):
    with self.db.connect() as conn:
        query = 'SELECT * FROM expenses WHERE 1=1'
        params = []
        if category_id is not None:
            query = query + ' AND category_id = ?'
            params.append(category_id)
        if start_date is not None:
            query = query + ' AND expense_date >= ?'
            params.append(start_date)
        return [dict(r) for r in conn.execute(query, params).fetchall()]
""", False),
    ("""def list_books(self, available_only):
    with self.db.connect() as conn:
        query = 'SELECT * FROM books WHERE 1=1'
        if available_only:
            query += ' AND available_copies > 0'
        return [dict(r) for r in conn.execute(query).fetchall()]
""", False),
    ("""def list_loans(self):
    import datetime
    with self.db.connect() as conn:
        stamp = datetime.datetime.now().isoformat()
        return [dict(r) for r in conn.execute('SELECT * FROM loans', ()).fetchall()]
""", False),
    ("""def check_budget_exceeded(self, category_id, month):
    period = str(month)[:7]
    limit = None
    for _row in self.list(category_id=category_id):
        if str(_row.month)[:7] == period:
            limit = int(_row.amount_limit_cents or 0)
            break
    if limit is None:
        return 'on_track'
    return 'exceeded' if limit == 0 else 'on_track'
""", False),
]


def suite_fidelity_rules() -> Suite:
    import ast
    from agentlib.generation.repo_render import _repo_fidelity_violations

    s = Suite("fidelity-rules")
    for i, (src, want_bad) in enumerate(FIDELITY_CASES, 1):
        fn = ast.parse(src).body[0]
        viol = _repo_fidelity_violations(fn)
        s.check(
            "case %d is %s" % (i, "rejected" if want_bad else "accepted"),
            bool(viol) == want_bad,
            "; ".join(viol)[:160],
        )
    return s


SUITES = {
    "expenses": suite_expenses,
    "library_system": suite_library_system,
    "source-fidelity": suite_source_fidelity,
    "fidelity-rules": suite_fidelity_rules,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", action="append",
                        help="Only run these projects (repeatable)")
    args = parser.parse_args(argv)

    idents = args.prompt or list(SUITES)
    unknown = [i for i in idents if i not in SUITES]
    if unknown:
        print("no behavioural suite for: %s" % ", ".join(unknown),
              file=sys.stderr)
        return 1

    all_ok = True
    for ident in idents:
        suite = SUITES[ident]()
        print("== %s ==" % ident)
        if not suite.report():
            all_ok = False
    print("\n[cli-behavior] %s" % ("PASS" if all_ok else "FAIL"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
