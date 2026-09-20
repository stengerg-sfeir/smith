"""Enforce the ORDER of a spec-declared time pair on the create path.

"Each appointment must always end after it starts, but the application must
also support appointments whose start and end time are identical" (prompt 54)
states a comparison the create path never made: the filled `add_appointment`
built the row without looking at either value, and the one check the design DID
write (`if start_time >= end_time`) lived in an unrelated read-only method. So a
backwards appointment was accepted while the prompt's own rule was unenforced.

The guard is the prompt's comparison, verbatim:

* an end that sorts BEFORE its start is refused;
* an IDENTICAL pair is accepted (the prompt says so explicitly) — hence a
  strict `<`, never `<=`.

Values reach a service as ISO-format strings (the same convention the rest of
the generated code uses for date columns), so the comparison is a plain string
comparison of two ISO stamps — no parsing, no library, and no assumption about
which of the two columns is a date and which a datetime.
"""
from __future__ import annotations

import ast

from .field_guard import _method_named, _snake_name, inject_guards

_MARKER = "# time pair guard (spec)"
_TIME_HINTS = ("time", "date", "range", "appointment", "booking", "schedule")
_GENERIC_EXCEPTIONS = ("ValidationError", "InvalidValueError", "ValueError")


def pick_time_exception(exception_names):
    """The exception a backwards pair should raise, from the design's naming."""
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    for hint in _TIME_HINTS:
        for name in sorted(names):
            low = name.lower()
            if hint in low and "notfound" not in low and "missing" not in low:
                return name
    for want in _GENERIC_EXCEPTIONS:
        if want in names:
            return want
    return "ValueError"


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


def guard_lines(start_field, end_field, args, exception_names, entity):
    """The refusal lines, or None when either name is not a parameter."""
    if args is None or start_field not in args or end_field not in args:
        return None
    exc = pick_time_exception(exception_names)
    return [
        "        " + _MARKER,
        "        if %s is not None and %s is not None and str(%s) < str(%s):"
        % (end_field, start_field, end_field, start_field),
        "            raise %s(%r)"
        % (exc, "a %s must not end before it starts" % entity),
    ]


def apply_time_pair_guard(svc_source, cls, pair, exception_names):
    """Return ``svc_source`` with the pair order enforced on creation.

    ``pair`` is the (start_field, end_field) NAMES the design declared. Additive
    and idempotent; a no-op when the create method is absent or either name is
    not one of its parameters (a guard is never invented).
    """
    if not svc_source or not pair:
        return svc_source
    if _MARKER in svc_source:
        return svc_source
    start, end = pair
    ent_snake = _snake_name(cls)
    for name in ("add_" + ent_snake, "create_" + ent_snake):
        args = _service_args(svc_source, name)
        lines = guard_lines(start, end, args, exception_names, ent_snake)
        if lines:
            svc_source = inject_guards(svc_source, name, lines)
    return svc_source
