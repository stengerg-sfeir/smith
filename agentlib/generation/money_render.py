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


def spec_declares_money_display(prompt_text):
    """True when the specification asks for cents storage AND decimal display.

    Both halves are required: a specification that only mentions cents
    (storage) is left untouched.
    """
    text = prompt_text or ""
    return bool(_CENTS_RE.search(text) and _DECIMAL_RE.search(text))


def money_field_names(entities_by_class):
    """Sorted ``*_cents`` field names across the designed entities."""
    names = set()
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
        money_field_names(entities_by_class)
    )


def render_money_module():
    """The ``money.py`` source shipped with the project."""
    return _MONEY_SOURCE


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


def is_money_field(name: Any) -> bool:
    """True when a field/variable name carries a cents amount."""
    return isinstance(name, str) and name.endswith("_cents")


def format_result(result: Any) -> str:
    """A console string for a result, every *_cents value shown as a decimal.

    A result carrying no cents value renders exactly as it did before, so an
    unrelated command's output never changes.
    """
    return _render(result)


def _render(value: Any) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(
            "%r: %s" % (
                key,
                format_money(val) if is_money_field(key) else _render(val),
            )
            for key, val in value.items()
        ) + "}"
    if isinstance(value, (list, tuple, set)):
        inner = ", ".join(_render(item) for item in value)
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
                    format_money(getattr(value, field_name))
                    if is_money_field(field_name)
                    else _render(getattr(value, field_name)),
                )
                for field_name in fields
            ),
        )
    return repr(value)
'''
