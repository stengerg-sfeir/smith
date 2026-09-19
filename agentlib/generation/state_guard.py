"""Inject spec-declared STATE TRANSITIONS into the rendered service methods.

``state_rules.extract_state_rules`` reads the prompt's state machine ("A
cancelled order cannot be shipped, and a shipped order cannot be cancelled",
prompt 32); this module turns each refused move into a guard at the top of the
operation method that performs it.

Why inject instead of re-rendering the body: the shipped operations are not
empty — they already load the row, set the target state and refuse the
IDEMPOTENT repeat ("if row.status == 'shipped': return False"). That half is
correct and worth keeping; only the TRANSITION half is missing. The guard is
therefore spliced AFTER the row is loaded (the guard reads it) and BEFORE the
first write, leaving everything else byte for byte.

The operation is resolved from the METHOD NAMES themselves — ``ship_order``
performs the move into ``shipped`` because ``ship`` is a prefix of the target
state — so no surface or CLI knowledge is needed, and an operation the design
did not create is simply not guarded.
"""
from __future__ import annotations

import ast

from .field_guard import _method_named, _snake_name

_MARKER = "# state transition (spec)"
_DEFAULT_EXCEPTION = "ValidationError"
_STATE_EXCEPTION_NAMES = (
    "InvalidStateError",
    "InvalidTransitionError",
    "StateTransitionError",
    "InvalidStatusError",
    "ValidationError",
    "InvalidValueError",
    "ValueError",
)
# Exception names that describe a refused state change, in preference order.
_STATE_HINTS = ("state", "transition", "status", "invalid")


def pick_state_exception(exception_names):
    """The exception a refused transition should raise.

    The design's OWN naming decides: a class mentioning the state machine
    (``InvalidStateError``/``InvalidTransitionError``) is exactly the one it
    declared for this refusal. Falls back to the generic validation names and
    then the builtin ``ValueError`` — a refusal is never a silent pass.
    """
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    for hint in _STATE_HINTS:
        for name in sorted(names):
            if hint in name.lower():
                return name
    for want in _STATE_EXCEPTION_NAMES:
        if want in names:
            return want
    return _DEFAULT_EXCEPTION if _DEFAULT_EXCEPTION in names else "ValueError"


def _is_row_none_guard(node):
    """True for ``if row is None: ...``."""
    if not isinstance(node, ast.If):
        return False
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "row"
        and any(isinstance(op, ast.Is) for op in test.ops)
        and any(isinstance(c, ast.Constant) and c.value is None
                for c in test.comparators)
    )


def _anchor_line(method):
    """1-based line to insert the guard AFTER, or None.

    The guard READS ``row``, so it must run after the row is loaded — and,
    crucially, AFTER a ``if row is None: raise <NotFound>`` guard when one
    follows: splicing between the two would make a missing row raise
    ``AttributeError`` on ``row.status`` instead of the not-found error the
    design declared. The anchor is therefore the not-found guard's last line
    when it is the statement right after the load, and the load's own last
    line otherwise.
    """
    body = list(method.body)
    for i, node in enumerate(body):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        value = node.value
        if not (isinstance(target, ast.Name) and target.id == "row"):
            continue
        if not (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)):
            continue
        src = value.func.value
        if not (
            isinstance(src, ast.Attribute)
            and src.attr.endswith("_repo")
            and isinstance(src.value, ast.Name)
            and src.value.id == "self"
        ):
            continue
        if i + 1 < len(body) and _is_row_none_guard(body[i + 1]):
            return body[i + 1].end_lineno
        return node.end_lineno
    return None


def _method_names(source):
    """Every method name in the rendered service (descending into classes)."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return []
    names = []
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.append(sub.name)
    return names


def _op_for_state(state, entity_snake, method_names):
    """The method performing the move INTO ``state``, or None.

    ``ship_order`` performs the move into ``shipped``: the method's verb is a
    prefix of the target state. The LONGEST such prefix wins, so ``cancel``
    beats ``can`` if both somehow existed, and a verb shorter than three
    characters is ignored rather than matching everything.
    """
    best = None
    for name in method_names:
        if not name.endswith("_" + entity_snake):
            continue
        verb = name[: -len("_" + entity_snake)]
        if len(verb) < 3 or not state.startswith(verb):
            continue
        if best is None or len(verb) > len(best):
            best = verb
    return None if best is None else "%s_%s" % (best, entity_snake)


def inject_state_guards(source, method_name, guard_lines):
    """Splice ``guard_lines`` AFTER the row load of ``method_name``.

    Returns the new source unchanged when the method is absent, the source
    does not parse, the guard was already injected (the marker is present) or
    there is nothing to inject — so a re-render never doubles a guard.
    """
    if not source or not guard_lines:
        return source
    try:
        tree = ast.parse(source)
    except (SyntaxError, TypeError, ValueError):
        return source
    method = _method_named(tree, method_name)
    if method is None:
        return source
    lines = source.splitlines(keepends=True)
    anchor = _anchor_line(method)
    if anchor is not None:
        start = anchor  # insert on the line right AFTER the load
    else:
        start = method.body[0].lineno - 1
    if start < 0 or start > len(lines):
        return source
    window = "".join(lines[max(0, start - 6):start + 12])
    if _MARKER in window:
        return source
    block = "".join(line + "\n" for line in guard_lines)
    return "".join(lines[:start]) + block + "".join(lines[start:])


def apply_state_guards(source, cls, rules, exception_names):
    """Inject every refused transition of ``cls`` into its operation methods."""
    if not source or not rules:
        return source
    entity_snake = _snake_name(cls)
    field = rules.get("field")
    forbidden = rules.get("forbidden") or []
    if not field or not forbidden:
        return source
    names = _method_names(source)
    by_method: dict[str, list[str]] = {}
    for pair in forbidden:
        method_name = _op_for_state(pair["to"], entity_snake, names)
        if method_name is None:
            continue
        exc = pick_state_exception(exception_names)
        message = "a %s %s cannot be %s" % (
            pair["from"], entity_snake, pair["to"],
        )
        by_method.setdefault(method_name, [])
        by_method[method_name] += [
            "        " + _MARKER,
            "        if row.%s == %r:" % (field, pair["from"]),
            "            raise %s(%r)" % (exc, message),
        ]
    for method_name, guard_lines in by_method.items():
        source = inject_state_guards(source, method_name, guard_lines)
    return source
