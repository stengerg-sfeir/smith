"""Decimal display helpers for projects that store money as integer cents.

The specification's money convention is two-sided: values are STORED as
integer cents (no floating point anywhere — the schema enforces it) and
CONVERTED to/from decimal FOR DISPLAY. The storage half is already
deterministic in the renderers; this module renders the display half as a
small, importable helper the shipped project actually uses. Generated
projects contained no decimal conversion at all, so the requirement was
silently unimplemented.

Bounded on purpose: the module is emitted only for a specification that
declares BOTH cents-based storage AND a decimal conversion, and only when the
design actually carries a ``*_cents`` field to convert — so a specification
that mentions cents but never asks for display conversion keeps byte-identical
CLI output.
"""
import re

_CENTS_RE = re.compile(r"\bcents?\b", re.IGNORECASE)
_DECIMAL_RE = re.compile(r"\bdecimal\b", re.IGNORECASE)

MONEY_MODULE = "money.py"

# ``<field> (<type>, stored as cents)`` — the specification naming a field
# whose VALUE is a count of cents even though its name does not say so.
# Expenses writes ``monthly_budget (optional int, stored as cents)``: the
# design carries the field, but no ``*_cents`` suffix marks it, so the
# display half of the convention never reached it and ``category list``
# printed ``monthly_budget=50000`` next to an ``amount_cents=12.50``. The
# declaration is in the SPECIFICATION, so it is read from there.
# A TYPE word is required inside the parentheses too. Expenses' general
# sentence "All monetary values must be stored as integers (cents)" also has
# a word followed by "(cents)" — ``integers (cents)`` — and would otherwise be
# read as a field declaration, putting ``integers`` in the money set. A real
# declaration always names a type next to the unit
# (``monthly_budget (optional int, stored as cents)``).
_TYPE_WORD = (
    r"(?:int|integer|str|string|float|bool|boolean|decimal|date|datetime"
    r"|text|numeric)"
)
_FIELD_CENTS_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*\([^)]*\b%s\b[^)]*\bcents?\b[^)]*\)" % _TYPE_WORD
)


def spec_money_field_names(prompt_text):
    """Field names the SPECIFICATION declares as stored-in-cents."""
    return sorted(set(_FIELD_CENTS_RE.findall(prompt_text or "")))


def spec_declares_money_display(prompt_text):
    """True when the specification asks for cents storage AND decimal display.

    Both halves are required: a specification that only mentions cents
    (storage) is left untouched.
    """
    text = prompt_text or ""
    return bool(_CENTS_RE.search(text) and _DECIMAL_RE.search(text))


def money_field_names(entities_by_class, prompt_text=None):
    """Sorted field names that carry a count of cents.

    Two sources, both declarations: the DESIGN's own ``*_cents`` column
    names, and the fields the SPECIFICATION marks "stored as cents" whatever
    their spelling. A field the specification declares as cents is money
    everywhere — storage, the CLI option that feeds it, and display — so the
    three must agree on the same set.
    """
    names = set(spec_money_field_names(prompt_text))
    for ent in (entities_by_class or {}).values():
        if not isinstance(ent, dict):
            continue
        for f in ent.get("fields") or []:
            if not isinstance(f, dict):
                continue
            name = f.get("name")
            if isinstance(name, str) and name.endswith("_cents"):
                names.add(name)
    return sorted(names)


def money_display_enabled(prompt_text, entities_by_class):
    """True only when both the specification and the design ask for it."""
    return spec_declares_money_display(prompt_text) and bool(
        money_field_names(entities_by_class, prompt_text)
    )


def render_money_module(money_names=None):
    """The ``money.py`` source shipped with the project.

    The field names are BAKED IN: the module converts by declared identity,
    not by a ``_cents`` suffix guess, so a field the specification declared
    as cents (``monthly_budget``) is converted exactly like a ``_cents`` one.
    """
    names = ", ".join(repr(n) for n in (money_names or ()))
    return _MONEY_SOURCE.replace("__MONEY_FIELDS__", names)


_MONEY_SOURCE = '''"""Decimal display helpers for money stored as integer cents.

Storage is always an INTEGER number of cents (the database schema enforces
it); this module is the only place that converts between that integer and a
decimal amount, so display never involves floating point.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

_CENT = Decimal("0.01")


def to_decimal(cents: Any) -> Decimal:
    """The decimal AMOUNT of a cent integer (1250 -> Decimal("12.50"))."""
    return (Decimal(int(cents)) / 100).quantize(
        _CENT, rounding=ROUND_HALF_UP
    )


def from_decimal(amount: Any) -> int:
    """Integer cents for a decimal amount (Decimal("12.50") -> 1250).

    An ``int`` is already a count of cents and is returned UNCHANGED, so a
    caller that speaks cents is never rescaled. A ``Decimal`` (or a string
    such as ``"12.50"``) is read as a decimal AMOUNT and scaled by 100.
    """
    if isinstance(amount, bool):
        raise ValueError(
            "a money amount must be an int, a Decimal or a decimal string"
        )
    if isinstance(amount, int):
        return amount
    value = amount if isinstance(amount, Decimal) else Decimal(str(amount))
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money(cents: Any) -> str:
    """The display form of a cent integer ("12.50")."""
    return str(to_decimal(cents))


# The fields the generator declared as money: the design's own ``*_cents``
# columns plus the fields the SPECIFICATION marks "stored as cents". The list
# is baked in at generation time, so a declared money field whose name says
# nothing about cents (``monthly_budget``) is converted exactly like the rest.
_MONEY_FIELDS = frozenset([__MONEY_FIELDS__])


def is_money_field(name: Any) -> bool:
    """True when a field/variable name carries a cents amount."""
    return isinstance(name, str) and name in _MONEY_FIELDS


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, Decimal)) and not isinstance(
        value, bool
    )


def _money(value: Any, money: Any) -> str:
    """The decimal form of a money value, else its normal rendering."""
    return format_money(value) if _is_number(value) else _render(value, money)


def format_result(result: Any, money: Any = None) -> str:
    """A console string for a result, every money value shown as a decimal.

    ``money`` names the RESULT KEYS whose value is money but whose key is not
    a column name — the aggregate keys a report builds ("total",
    "per_category", "monthly_totals", "average_monthly_spend"). A key mapped
    to ``"map"`` holds a mapping of money values; a key mapped to ``"scalar"``
    holds one. An empty mapping means "decide by field name alone", so a
    command that returns plain rows renders as before.
    """
    return _render(result, money or {})


def _render(value: Any, money: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, val in value.items():
            kind = money.get(key) if isinstance(key, str) else None
            if kind == "map" and isinstance(val, dict):
                shown = "{" + ", ".join(
                    "%r: %s" % (k, _money(v, money))
                    for k, v in val.items()
                ) + "}"
            elif kind == "scalar" or is_money_field(key):
                shown = _money(val, money)
            else:
                shown = _render(val, money)
            parts.append("%r: %s" % (key, shown))
        return "{" + ", ".join(parts) + "}"
    if isinstance(value, (list, tuple, set)):
        inner = ", ".join(_render(item, money) for item in value)
        if isinstance(value, tuple):
            return "(" + inner + ("," if len(value) == 1 else "") + ")"
        if isinstance(value, set):
            return "{" + inner + "}"
        return "[" + inner + "]"
    fields = getattr(type(value), "__dataclass_fields__", None)
    if fields:
        return "%s(%s)" % (
            type(value).__name__,
            ", ".join(
                "%s=%s" % (
                    field_name,
                    _money(getattr(value, field_name), money)
                    if is_money_field(field_name)
                    else _render(getattr(value, field_name), money),
                )
                for field_name in fields
            ),
        )
    return repr(value)
'''
