"""Enforce a spec-declared OVERLAP rule: no two overlapping periods per resource.

``overlap_rules.extract_overlap_rules`` reads the prompt ("A room cannot have
two overlapping reservations", prompt 27); this module makes the rule hold:

* the RESERVATION repository gains ``has_overlapping_reservation(room_id,
  start_date, end_date)`` — a single SQL existence test, the same shape every
  other repository method uses (``with self.db.connect() as conn:``);
* the service's create path refuses BEFORE inserting, so nothing is written
  when the period is taken.

Two details are deliberate:

* the table name is READ BACK from the rendered repository (its own ``FROM``
  clause) instead of re-derived — the renderer is the authority on the table
  the class actually queries;
* the guard's arguments are the SERVICE method's own parameter names, matched
  against the model's field names. When a name does not line up the guard is
  dropped rather than invented, because calling the overlap test with the
  wrong argument would silently check the wrong column.
"""
from __future__ import annotations

import ast
import re

from .field_guard import _method_named, _snake_name, inject_guards

_MARKER = "# overlap guard (spec)"
_TABLE_RE = re.compile(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)")
_DEFAULT_EXCEPTION = "ValidationError"
_OVERLAP_HINTS = ("overlap", "conflict", "unavailable", "double", "already")
_GENERIC_EXCEPTIONS = (
    "ValidationError",
    "InvalidValueError",
    "ConflictError",
    "ValueError",
)


def pick_overlap_exception(exception_names):
    """The exception an overlapping booking should raise.

    The design's own naming decides (``OverlapError``/``RoomUnavailableError``
    name this refusal exactly); failing that the generic validation names, then
    the builtin ``ValueError`` — a refusal is never a silent pass.
    """
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    for hint in _OVERLAP_HINTS:
        for name in sorted(names):
            if hint in name.lower():
                return name
    for want in _GENERIC_EXCEPTIONS:
        if want in names:
            return want
    return _DEFAULT_EXCEPTION if _DEFAULT_EXCEPTION in names else "ValueError"


def _table_from_source(repo_source):
    """The table the rendered repository queries (its own ``FROM`` clause)."""
    m = _TABLE_RE.search(repo_source or "")
    return m.group(1) if m else None


def _class_body_end(source):
    """1-based line just after the module's class body, or None."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return None
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.ClassDef) and node.body:
            return node.body[-1].end_lineno
    return None


def repo_overlap_method(item_snake, rule, table, method_name):
    """The ``has_overlapping_<item>`` method, at class-body indentation."""
    fk = rule["fk_field"]
    start = rule["start_field"]
    end = rule["end_field"]
    sql = (
        "SELECT 1 FROM %s WHERE %s = ? AND %s < ? AND %s > ? LIMIT 1"
        % (table, fk, start, end)
    )
    return [
        "    def %s(self, %s: int, %s: str, %s: str) -> bool:"
        % (method_name, fk, start, end),
        '        """True when another %s for the same %s overlaps this period."""'
        % (item_snake, rule["resource"]),
        "        with self.db.connect() as conn:",
        "            row = conn.execute(",
        '                "%s",' % sql,
        "                (%s, %s, %s)," % (fk, end, start),
        "            ).fetchone()",
        "        return row is not None",
    ]


def _service_args(source, method_name):
    """The parameter names of ``method_name``, or None."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return None
    method = _method_named(tree, method_name)
    if method is None:
        return None
    return [a.arg for a in method.args.args]


def service_guard_lines(rule, item_snake, method_name, args, exception_names):
    """The create-path guard lines, or None when a needed name is missing."""
    fk = rule["fk_field"]
    start = rule["start_field"]
    end = rule["end_field"]
    needed = (fk, start, end)
    if args is None or not all(n in args for n in needed):
        return None
    exc = pick_overlap_exception(exception_names)
    message = "the %s already has an overlapping %s" % (
        rule["resource"], item_snake,
    )
    return [
        "        " + _MARKER,
        "        if self.%s_repo.has_overlapping_%s(%s, %s, %s):"
        % (item_snake, item_snake, fk, start, end),
        "            raise %s(%r)" % (exc, message),
    ]


def apply_overlap_guard(repo_source, svc_source, cls, rule, exception_names):
    """Return (repo_source, svc_source) with the overlap rule enforced.

    The repository gains the existence test; the service's create method
    refuses on a hit. Both edits are additive and idempotent, and either may
    be skipped (table unknown, method absent, argument names not matching)
    without touching the other.
    """
    if not rule:
        return repo_source, svc_source
    item_snake = _snake_name(cls)
    method_name = "has_overlapping_%s" % item_snake
    table = _table_from_source(repo_source)
    if table and repo_source and _MARKER not in repo_source:
        end = _class_body_end(repo_source)
        if end is not None:
            lines = repo_source.splitlines(keepends=True)
            block = "".join(
                line + "\n" for line in repo_overlap_method(
                    item_snake, rule, table, method_name
                )
            )
            repo_source = "".join(lines[:end]) + "\n" + block + "".join(lines[end:])
    for create_name in ("add_" + item_snake, "create_" + item_snake):
        args = _service_args(svc_source, create_name)
        guard = service_guard_lines(
            rule, item_snake, create_name, args, exception_names
        )
        if guard:
            svc_source = inject_guards(svc_source, create_name, guard)
    return repo_source, svc_source
