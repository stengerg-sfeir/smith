#!/usr/bin/env python3
"""Unit tests for the repository duplicate-pruners (deterministic, no LLM).

Pins BOTH directions of every predicate the sixth pass relies on, so a later
tweak to the spelling tables cannot silently start dropping a capability the
specification names, nor stop dropping a duplicate:

* ``_crud_shadow_target``   — R1, the CRUD re-spellings that must go, and the
  spec-named shapes that must survive;
* ``_qualifier_extension_of`` — R2, a sibling plus a scalar qualifier;
* ``_capability_tokens``    — the (verb, content tokens) reader both rely on;
* ``_unjustified_qualifier_customs`` — R3c, bullet-guarded count/total extras;
* ``_subsumed_by_sibling``  — R3e, a rejected body whose words a sibling names;
* ``_spelled_in_bullet``    — R3h, which of two spellings of ONE capability the
  repository's own specification bullet names, so the unspelled one is dropped
  (``list_authors_with_books`` beside ``find_books_by_author``);
* ``_drop_functions``       — the AST range deletion that removes them.

Usage: python3 run_repo_pruner_unit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# The repository root (agentlib/bench -> agentlib -> root) so `import agentlib`
# resolves when this module is run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from agentlib.generation.repo_render import (  # noqa: E402
    _capability_tokens,
    _crud_shadow_target,
    _drop_functions,
    _qualifier_extension_of,
    _stemmed_tokens,
    _subsumed_by_sibling,
    _unjustified_qualifier_customs,
)
from agentlib.pipeline.cli_surface import repo_spec_constraint  # noqa: E402
from agentlib.pipeline.manifest import (  # noqa: E402
    _ordered_tokens,
    _prune_uncalled_repo_customs,
    _spelled_in_bullet,
)

_FAILURES: list[str] = []


def _check(label: str, got, want) -> None:
    if got != want:
        _FAILURES.append("%s: got %r, want %r" % (label, got, want))


# --- R1: the CRUD re-spelling that must be pruned, per entity --------------
_SHADOWS = [
    ("add_member", "member", "Member", "create"),
    ("list_members", "member", "Member", "list"),
    ("list_books", "book", "Book", "list"),
    ("list_expenses", "expense", "Expense", "list"),
    ("list_categories", "category", "Category", "list"),
    ("list_budgets", "budget", "Budget", "list"),
    ("add_category", "category", "Category", "create"),
    ("add_budget", "budget", "Budget", "create"),
    ("update_category", "category", "Category", "update"),
    ("update_budget", "budget", "Budget", "update"),
    ("delete_category", "category", "Category", "delete"),
    ("delete_budget", "budget", "Budget", "delete"),
    ("get_expense_by_id", "expense", "Expense", "get_by_id"),
    ("get_category_by_id", "category", "Category", "get_by_id"),
    ("get_member_by_id", "member", "Member", "get_by_id"),
    ("find_book_by_id", "book", "Book", "get_by_id"),
    ("insert_loan", "loan", "Loan", "create"),
    ("remove_member", "member", "Member", "delete"),
    ("edit_budget", "budget", "Budget", "update"),
    ("get_all_expenses", "expense", "Expense", "get_all"),
    ("list_all_budgets", "budget", "Budget", "list"),
]

# --- R1: the capabilities that MUST be kept (they keep a non-entity token) --
_KEPT = [
    ("search_books", "book", "Book"),
    ("find_books_by_author", "author", "Author"),
    ("get_expenses_for_category", "category", "Category"),
    ("get_overdue_loans", "loan", "Loan"),
    ("get_active_loans", "loan", "Loan"),
    ("get_member_loan_history", "loan", "Loan"),
    ("get_book_loan_history", "loan", "Loan"),
    ("get_overdue_loans_count", "loan", "Loan"),
    ("list_authors_with_books", "author", "Author"),
    ("get_author_books_count", "author", "Author"),
    ("get_member_history", "member", "Member"),
    ("get_monthly_report", "expense", "Expense"),
    ("get_yearly_summary", "expense", "Expense"),
    ("get_category_spending", "expense", "Expense"),
    ("export_to_csv", "expense", "Expense"),
    ("detect_recurring", "expense", "Expense"),
    ("check_budget_exceeded", "budget", "Budget"),
    ("get_by_category_and_month", "budget", "Budget"),
    ("get_total_stock_value_by_category", "product", "Product"),
    ("find_low_stock_products", "product", "Product"),
]

# The deterministic surface itself is never a "custom".
_BASE = [
    ("create", "expense", "Expense"),
    ("get_by_id", "expense", "Expense"),
    ("get_all", "expense", "Expense"),
    ("list", "expense", "Expense"),
    ("update", "expense", "Expense"),
    ("delete", "expense", "Expense"),
]

_QUALIFIER_EXTENSIONS = [
    ("get_overdue_loans_count", "get_overdue_loans", True),
    ("get_overdue_loans", "get_overdue_loans_count", False),
    ("get_expenses_for_category", "get_expenses", False),
    ("get_active_loans", "get_overdue_loans", False),
    ("get_member_loan_history", "get_book_loan_history", False),
    ("get_yearly_summary", "get_monthly_report", False),
]

_CAPABILITIES = [
    ("list_authors_with_books", "author", "Author", ("list", {"books"})),
    ("find_books_by_author", "author", "Author", ("find", {"books"})),
    ("get_author_books_count", "author", "Author", ("get", {"books", "count"})),
    ("get_overdue_loans", "loan", "Loan", ("get", {"overdue"})),
    ("search_books", "book", "Book", ("search", set())),
    ("export_to_csv", "expense", "Expense", ("export", {"csv"})),
    ("get_expenses_for_category", "category", "Category", ("get", {"expenses"})),
]

_AUTHOR_BULLET = "AuthorRepository — SQLite storage with CRUD + find books by author"
_EXPENSE_BULLET = (
    "ExpenseRepository — SQLite storage with CRUD + filtering by date range, "
    "category, payment_method + monthly/yearly aggregation queries"
)

_DROP_SOURCE = (
    "class R:\n"
    "    def keep_me(self):\n"
    "        return 1\n"
    "\n"
    "    def drop_me(self):\n"
    "        return 2\n"
    "\n"
    "    def keep_too(self):\n"
    "        return 3\n"
)


def main(argv: list[str] | None = None) -> int:
    for name, ent, model, want in _SHADOWS:
        _check("R1 shadow %s" % name,
               _crud_shadow_target(name, ent, model), want)
    for name, ent, model in _KEPT + _BASE:
        _check("R1 keep %s" % name,
               _crud_shadow_target(name, ent, model), None)

    for a, b, want in _QUALIFIER_EXTENSIONS:
        _check("R2 %s vs %s" % (a, b), _qualifier_extension_of(a, b), want)

    for name, ent, model, want in _CAPABILITIES:
        _check("capability %s" % name,
               _capability_tokens(name, ent, model), want)

    # R3c — only when the repository has a specification bullet, and never for
    # a qualifier the bullet names.
    author_customs = [{"name": "find_books_by_author"},
                      {"name": "get_author_books_count"},
                      {"name": "list_authors_with_books"}]
    _check("R3c drops the unjustified count",
           [m["name"] for m in _unjustified_qualifier_customs(
               author_customs, _AUTHOR_BULLET, "author", "Author")],
           ["find_books_by_author", "list_authors_with_books"])
    _check("R3c is inert without a bullet",
           [m["name"] for m in _unjustified_qualifier_customs(
               author_customs, "", "author", "Author")],
           ["find_books_by_author", "get_author_books_count",
            "list_authors_with_books"])
    expense_customs = [{"name": n} for n in (
        "get_monthly_report", "get_yearly_summary", "get_category_spending",
        "export_to_csv", "detect_recurring")]
    _check("R3c keeps every non-qualifier custom",
           [m["name"] for m in _unjustified_qualifier_customs(
               expense_customs, _EXPENSE_BULLET, "expense", "Expense")],
           [m["name"] for m in expense_customs])

    # R3e — subsumed by a shipped sibling, and the two non-subsumed shapes.
    siblings = ["find_books_by_author", "search_books", "get_active_loans",
                "get_overdue_loans"]
    _check("R3e subsumes list_authors_with_books",
           _subsumed_by_sibling("list_authors_with_books", siblings,
                                "author", "Author"), True)
    _check("R3e never subsumes an entity-wide reading",
           _subsumed_by_sibling("search_books", ["get_active_loans"],
                                "book", "Book"), False)
    _check("R3e never subsumes a distinct reading",
           _subsumed_by_sibling("get_active_loans", ["get_overdue_loans"],
                                "loan", "Loan"), False)

    # R3h — the bullet's own spelling decides between two unreached methods
    # that name the SAME capability.
    author_seq = _ordered_tokens(_AUTHOR_BULLET)
    _check("R3h ordered tokens keep the phrase",
           author_seq[author_seq.index("find"):][:4],
           ["find", "books", "by", "author"])
    _check("R3h spells find_books_by_author",
           _spelled_in_bullet("find_books_by_author", author_seq), True)
    _check("R3h does not spell list_authors_with_books",
           _spelled_in_bullet("list_authors_with_books", author_seq), False)
    _check("R3h does not spell search_books",
           _spelled_in_bullet("search_books", author_seq), False)
    _check("R3h never spells the empty name",
           _spelled_in_bullet("", author_seq), False)

    # R3h end-to-end: the two spellings of AuthorRepository's find-books duty,
    # neither called by the shipped service, with the REAL prompt bullet.
    author_prompt = (Path("prompts") / "prompt_library_system.txt").read_text(
        encoding="utf-8")
    _check("R3h the prompt yields a bullet",
           bool(repo_spec_constraint(author_prompt, "author")), True)
    author_src = (
        "class AuthorRepository:\n"
        "    def find_books_by_author(self, author_id):\n"
        "        return []\n"
        "\n"
        "    def list_authors_with_books(self, include_inactive):\n"
        "        return []\n"
    )
    author_designs = [(
        "author_repository.py", "repositories",
        {"methods": [{"name": "find_books_by_author"},
                     {"name": "list_authors_with_books"}]},
    )]
    author_files = {"author_repository.py": author_src}
    _prune_uncalled_repo_customs(
        ["author_repository.py"], author_designs, author_files,
        "class S:\n    def m(self):\n        return None\n", author_prompt,
    )
    _check("R3h keeps only the spelled method",
           [m["name"] for m in author_designs[0][2]["methods"]],
           ["find_books_by_author"])
    _check("R3h drops the unspelled body",
           "list_authors_with_books" in author_files["author_repository.py"],
           False)
    _check("R3h keeps the spelled body",
           "find_books_by_author" in author_files["author_repository.py"], True)

    # The negative direction: two DISTINCT capabilities are both kept.
    expense_prompt = (Path("prompts") / "prompt_expenses.txt").read_text(
        encoding="utf-8")
    expense_src = (
        "class ExpenseRepository:\n"
        "    def get_monthly_report(self, month):\n"
        "        return {}\n"
        "\n"
        "    def get_yearly_summary(self, year):\n"
        "        return {}\n"
    )
    expense_designs = [(
        "expense_repository.py", "repositories",
        {"methods": [{"name": "get_monthly_report"},
                     {"name": "get_yearly_summary"}]},
    )]
    expense_files = {"expense_repository.py": expense_src}
    _prune_uncalled_repo_customs(
        ["expense_repository.py"], expense_designs, expense_files,
        "class S:\n    def m(self):\n        return None\n", expense_prompt,
    )
    _check("R3h keeps two distinct capabilities",
           [m["name"] for m in expense_designs[0][2]["methods"]],
           ["get_monthly_report", "get_yearly_summary"])

    # _drop_functions — removes exactly the named method, keeps the siblings,
    # leaves a parseable file, and no-ops on an empty set.
    out = _drop_functions(_DROP_SOURCE, ["drop_me"])
    _check("drop_functions removes the target", "drop_me" in out, False)
    _check("drop_functions keeps the first sibling", "keep_me" in out, True)
    _check("drop_functions keeps the second sibling", "keep_too" in out, True)
    _check("drop_functions keeps the body", "return 3" in out, True)
    _check("drop_functions no-ops on empty",
           _drop_functions(_DROP_SOURCE, []), _DROP_SOURCE)

    _check("stemmed tokens pluralise", "category" in _stemmed_tokens("categories"),
           True)

    n_cases = (len(_SHADOWS) + len(_KEPT) + len(_BASE)
               + len(_QUALIFIER_EXTENSIONS) + len(_CAPABILITIES) + 21)
    if _FAILURES:
        print("FAILURES: %d" % len(_FAILURES))
        for f in _FAILURES:
            print("  - " + f)
        return 1
    print("REPO PRUNERS: PASS (%d case(s))" % n_cases)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
