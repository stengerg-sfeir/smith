"""Value vocabularies the SPECIFICATION declares for a field.

Two prompts state a field's allowed values inline:

    payment_method (cash/card/transfer)   -> payment_method: cash, card, transfer
    status (active/returned/overdue)      -> status:         active, returned, overdue

That declaration is a VALUE CONVENTION: the field's domain. Nothing enforced
it, so ``expense add --method bitcoin`` was accepted and stored — a value the
specification never allowed.

The rule is conservative in two ways, because a parenthesised slash-list is
also how prose mentions a set of STATES rather than a field:

1. Only a name a DESIGNED ENTITY declares as a field is kept (the caller
   filters on the design), so ``budget status (on_track/warning/exceeded)``
   cannot constrain anything on its own.
2. A name whose occurrences DISAGREE is dropped entirely. library_system
   writes both ``status (active/returned/overdue)`` (the Loan column) and
   ``budget status (on_track/warning/exceeded)`` (a report's states), so the
   name is ambiguous and NO constraint is emitted — the same
   unique-alias-otherwise-refuse discipline the CLI option binding uses.

Nothing is invented: every value comes from the specification's own text.
"""
import re

# ``<name> (<v1>/<v2>/...)`` — at least two slash-separated vocabulary words.
_ENUM_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)")
_VALUE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def spec_enum_values(prompt_text):
    """{field: [values]} for every UNAMBIGUOUS slash-list the spec declares."""
    seen = {}
    for name, inner in _ENUM_RE.findall(prompt_text or ""):
        if "/" not in inner:
            continue
        values = [v.strip().lower() for v in inner.split("/")]
        if len(values) < 2 or not all(_VALUE_RE.match(v) for v in values):
            continue
        if len(set(values)) != len(values):
            continue
        seen.setdefault(name, set()).add(tuple(values))
    return {
        name: list(lists.pop())
        for name, lists in seen.items()
        if len(lists) == 1
    }
