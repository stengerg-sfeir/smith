"""Render spec-declared field validations INTO the generated service.

``field_rules.extract_field_rules`` reads the prompt; this module turns each
rule into guard lines and splices them at the TOP of the entity's create/update
body. The splice is an AST-directed LINE insertion (never ``ast.unparse``), so
the rest of the rendered method — its locked skeleton, its fill, its
indentation — is untouched byte for byte.

Why splice instead of rendering inside the create recipe: the create body is
built by several tiers (impl dispatch, generic delegation, LLM fill) and a rule
must hold whichever tier produced it. Injecting at the method's first statement
covers them all, and a marker line makes the operation idempotent.
"""
from __future__ import annotations

import ast

_MARKER = "# field validation (spec)"

_DEFAULT_EXCEPTION = "ValidationError"
# The exception the design declares for a rejected value, in preference order.
_VALIDATION_EXCEPTION_NAMES = (
    "ValidationError",
    "InvalidEmailError",
    "InvalidValueError",
    "ValueError",
)


def pick_validation_exception(exception_names, field="", kind=""):
    """The exception a rejected value on ``field`` should raise.

    The design often declares a FIELD-SPECIFIC one — prompt 09's design names
    ``InvalidEmailError``, ``AgeOutOfRangeError`` and ``NegativeSalaryError``
    — so a rule prefers the declared name that mentions its own field, then the
    generic validation names, and only then the builtin ``ValueError``. Nothing
    declared for either is still a refusal, never a silent pass.
    """
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    if field:
        stem = field.replace("_", "").lower()
        for want in names:
            low = want.lower()
            if stem and stem in low:
                return want
    for want in _VALIDATION_EXCEPTION_NAMES:
        if want in names:
            return want
    return _DEFAULT_EXCEPTION if _DEFAULT_EXCEPTION in names else "ValueError"


# Numeric fields are NOT reliably typed by the design: prompt 09's
# ``add_employee`` declares ``salary: str`` (the CLI scrapes TEXT), so a bare
# ``salary <= 0`` raised ``TypeError: '<=' not supported between 'str' and
# 'int'`` — a traceback instead of a refusal. Every numeric guard coerces
# through ``float()`` inside a try, and a value that is not a number is a
# refusal like any other.
def _numeric_block(field, cond_tpl, msg, exception_name, allow_none):
    """Guard lines comparing a NUMERIC field, robust to a str-typed param."""
    var = "_v_%s" % field
    bad_msg = msg.replace("must be", "must be a number and", 1)
    body = [
        "try:",
        "    %s = float(%s)" % (var, field),
        "except (TypeError, ValueError):",
        "    raise %s(%r)" % (exception_name, bad_msg),
        "if %s:" % (cond_tpl % var),
        "    raise %s(%r)" % (exception_name, msg),
    ]
    if allow_none:
        body = ["if %s is not None:" % field] + [_indent(line) for line in body]
    return body


def _indent(line):
    return ("    " + line) if line.strip() else line


def _email_condition(field, allow_none):
    """A dependency-free email shape test on ``field``.

    Deliberately avoids ``re`` — the generated module may not import it, and a
    missing import would turn the guard into a crash. ``str()`` is applied so a
    non-str value is rejected rather than raising a TypeError.
    """
    value = "str(%s)" % field
    ok = '("%s" in %s and "%s" in %s.split("@")[-1] and " " not in %s)' % (
        "@", value, ".", value, value,
    )
    if allow_none:
        return "%s is not None and not %s" % (field, ok)
    return "not %s" % ok


def _num(value):
    """Render a numeric literal without a trailing ``.0`` on whole numbers."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def render_guards(field, rule, exception_name, allow_none=False):
    """Guard lines for ONE rule, at method-body indentation (8 spaces).

    ``allow_none`` is the update path: click hands ``None`` for an option the
    caller omitted, and ``None`` means "leave this column alone" — not "the
    value is invalid" — so the guard is skipped in that case only.
    """
    kind = rule.get("kind")
    if kind == "range":
        lo, hi = rule["lo"], rule["hi"]
        msg = "%s must be between %s and %s" % (field, _num(lo), _num(hi))
        cond_tpl = "not (%s <= %%s <= %s)" % (_num(lo), _num(hi))
        body = _numeric_block(field, cond_tpl, msg, exception_name, allow_none)
    elif kind == "positive":
        msg = "%s must be positive" % field
        body = _numeric_block(
            field, "%s <= 0", msg, exception_name, allow_none
        )
    elif kind == "email":
        cond = _email_condition(field, allow_none)
        msg = "%s must be a valid email address" % field
        body = [
            "if %s:" % cond,
            "    raise %s(%r)" % (exception_name, msg),
        ]
    else:
        return []
    return ["        " + _MARKER] + ["        " + line for line in body]


def _method_named(tree, name):
    """The method node called ``name``, or None.

    The rendered service is a CLASS holding its methods — ``EmployeeService``
    with ``add_employee`` inside it — so the search must descend into class
    bodies, not just scan module-level functions.
    """
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if sub.name == name:
                        return sub
    return None


def _first_body_line(method):
    """1-based line of the method's first EXECUTABLE statement.

    A leading docstring (or any leading constant expression) is skipped: the
    guards belong at the start of the real body, after it.
    """
    body = list(method.body)
    idx = 0
    while idx < len(body) and isinstance(body[idx], ast.Expr) and isinstance(
        getattr(body[idx], "value", None), ast.Constant
    ):
        idx += 1
    if idx >= len(body):
        last = body[-1] if body else method
        return getattr(last, "end_lineno", last.lineno) + 1
    return body[idx].lineno


def inject_guards(source, method_name, guard_lines):
    """Splice ``guard_lines`` at the top of ``method_name``'s body.

    Returns the new source. No-op (returning the input) when the method is
    absent, the source does not parse, the guard was already injected (the
    marker is present), or there is nothing to inject — so a re-render never
    doubles a guard.
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
    start = _first_body_line(method) - 1
    if start < 0 or start > len(lines):
        return source
    window = "".join(lines[max(0, start - 2):start + 12])
    if _MARKER in window:
        return source
    block = "".join(line + "\n" for line in guard_lines)
    return "".join(lines[:start]) + block + "".join(lines[start:])


def _snake_name(cls):
    """``EmployeeRecord`` -> ``employee_record`` (mirrors agentlib.naming)."""
    out = []
    for i, ch in enumerate(cls or ""):
        if ch.isupper() and i:
            prev_upper = (cls[i - 1].isupper())
            next_upper = (i + 1 < len(cls) and cls[i + 1].isupper())
            if not (prev_upper and next_upper):
                out.append("_")
        out.append(ch.lower())
    return "".join(out)


def apply_field_guards(source, cls, rules, exception_names):
    """Inject every rule for ``cls`` into its create AND update bodies.

    The specification states the domain once for the entity ("The email must be
    valid, age must be between 18 and 70") and it holds on every path that
    writes the column: ``add_<entity>`` (required values) and
    ``update_<entity>`` (optional ones, where ``None`` means "unchanged").
    """
    if not rules:
        return source
    var = _snake_name(cls)
    for method_name, allow_none in (
        ("add_" + var, False),
        ("create_" + var, False),
        ("update_" + var, True),
    ):
        guard_lines = []
        for rule in rules:
            # The exception is chosen PER FIELD: the design's own
            # ``AgeOutOfRangeError`` fits the age rule, ``NegativeSalaryError``
            # the salary one and ``InvalidEmailError`` the address one, so a
            # refusal never wears another field's name.
            exc = pick_validation_exception(
                exception_names, rule.get("field"), rule.get("kind")
            )
            guard_lines += render_guards(
                rule["field"], rule, exc, allow_none=allow_none
            )
        source = inject_guards(source, method_name, guard_lines)
    return source
