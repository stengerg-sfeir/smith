"""Enforce a spec-declared "at most one active row per resource" rule (C4).

``active_rules.extract_active_rules`` reads the prompt ("a book can have at
most one active loan", prompt 26); this module makes it hold:

* the LOAN repository gains ``has_active_loan(book_id)`` — one SQL existence
  test in the same shape every other repository method uses;
* the service's create path refuses BEFORE inserting, so a second loan for a
  book already on loan is never written.

The shape mirrors ``overlap_guard`` (which guards a date range the same way),
and the class-body splice/anchor helpers are shared with it rather than
duplicated.
"""
from __future__ import annotations

from .field_guard import _snake_name, inject_guards
from .overlap_guard import _class_body_end, _table_from_source

_MARKER = "# at-most-one-active guard (spec)"
_DEFAULT_EXCEPTION = "ValidationError"
_ACTIVE_HINTS = ("active", "already", "borrow", "unavailable", "invalid")
_GENERIC_EXCEPTIONS = (
    "ValidationError",
    "InvalidValueError",
    "ConflictError",
    "ValueError",
)


def pick_active_exception(exception_names):
    """The exception a second active loan should raise.

    The design's own naming decides (``AlreadyBorrowedError`` /
    ``BookUnavailableError`` name this refusal); failing that the generic
    validation names, then the builtin ``ValueError`` — never a silent pass.
    """
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    for hint in _ACTIVE_HINTS:
        for name in sorted(names):
            if hint in name.lower():
                return name
    for want in _GENERIC_EXCEPTIONS:
        if want in names:
            return want
    return _DEFAULT_EXCEPTION if _DEFAULT_EXCEPTION in names else "ValueError"


def repo_active_method(item_snake, rule, table, method_name):
    """The ``has_active_<item>`` method, at class-body indentation."""
    fk = rule["fk_field"]
    flag = rule["flag_field"]
    sql = "SELECT 1 FROM %s WHERE %s = ? AND %s = 1 LIMIT 1" % (table, fk, flag)
    return [
        "    def %s(self, %s: int) -> bool:" % (method_name, fk),
        '        """True when this %s already carries an active %s."""'
        % (rule["resource"], item_snake),
        "        with self.db.connect() as conn:",
        "            row = conn.execute(",
        '                "%s",' % sql,
        "                (%s,)," % fk,
        "            ).fetchone()",
        "        return row is not None",
    ]


def _service_args(source, method_name):
    """The parameter names of ``method_name``, or None."""
    from .overlap_guard import _service_args as _sa

    return _sa(source, method_name)


def service_guard_lines(rule, item_snake, args, exception_names):
    """The create-path guard lines, or None when the FK argument is missing."""
    fk = rule["fk_field"]
    if args is None or fk not in args:
        return None
    exc = pick_active_exception(exception_names)
    message = "the %s already has an active %s" % (rule["resource"], item_snake)
    return [
        "        " + _MARKER,
        "        if self.%s_repo.has_active_%s(%s):"
        % (item_snake, item_snake, fk),
        "            raise %s(%r)" % (exc, message),
    ]


def apply_active_guard(repo_source, svc_source, cls, rule, exception_names):
    """Return (repo_source, svc_source) with the rule enforced.

    Additive and idempotent; either half may be skipped (unknown table,
    absent method, FK argument not matching) without touching the other.
    """
    if not rule:
        return repo_source, svc_source
    item_snake = _snake_name(cls)
    method_name = "has_active_%s" % item_snake
    table = _table_from_source(repo_source)
    if table and repo_source and _MARKER not in repo_source:
        end = _class_body_end(repo_source)
        if end is not None:
            lines = repo_source.splitlines(keepends=True)
            block = "".join(
                line + "\n" for line in repo_active_method(
                    item_snake, rule, table, method_name
                )
            )
            repo_source = "".join(lines[:end]) + "\n" + block + "".join(lines[end:])
    for create_name in ("add_" + item_snake, "create_" + item_snake):
        args = _service_args(svc_source, create_name)
        guard = service_guard_lines(rule, item_snake, args, exception_names)
        if guard:
            svc_source = inject_guards(svc_source, create_name, guard)
    return repo_source, svc_source
