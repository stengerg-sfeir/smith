"""Spec-declared AMOUNT operations: a delta on a numeric field.

The specification sometimes states a state change as a delta on a stored number
WITHOUT naming the amount at all:

    "Deposits increase the balance and withdrawals decrease it.
     A withdrawal must be rejected if it would make the balance negative."
    (prompt 31)

Nothing downstream read that. The shipped ``account deposit`` / ``account
withdraw`` commands took only ``--id`` (no ``--amount``) and the service body
raised "Withdrawal amount is required but not provided" — so depositing and
withdrawing were both impossible.

The precise discriminator (and the reason this does NOT fire on the named
``inventory`` prompt, which says "restock(id, qty): increases a product's
stock_qty"): an implicit amount is synthesised ONLY when the specification does
not already NAME a parameter for that very operation. When it enumerates
``restock(id, qty)`` the amount is already the caller's ``qty``, and inventing a
second one would break a working surface.

Nothing here reads the generated code: the prompt is the only source, and every
field is bound to a numeric column of a DESIGNED entity.
"""
from __future__ import annotations

import re

# "<noun>s increase(s) the <field>" / "withdrawals decrease it" — the subject
# names the OPERATION, the direction the sign, the object the FIELD.
_DELTA_RE = re.compile(
    r"\b(?P<op>[a-z_]+)s?\s+(?P<dir>increase|increases|decrease|decreases)\s+"
    r"(?:the\s+|its\s+|a\s+|an\s+)?(?P<obj>[a-z_]+)\b",
    re.I,
)
# "A withdrawal must be rejected if it would make the balance negative" — the
# operation named here is refused when it would drive the field below zero.
_NEGATIVE_RE = re.compile(
    r"\b(?P<op>[a-z_]+)s?\s+must\s+be\s+rejected\s+if\s+it\s+would\s+make\s+"
    r"(?:the\s+|its\s+|a\s+|an\s+)?(?P<field>[a-z_]+)\s+negative\b",
    re.I,
)
_SIGN = {"increase": 1, "increases": 1, "decrease": -1, "decreases": -1}
_AMOUNT_PARAM = "amount"

# The specification names the operation as a NOUN ("deposits", "withdrawals")
# while the code names it as a VERB ("deposit", "withdraw"). A suffix that
# turns a verb into an operation noun is stripped so the two spellings meet:
# "withdrawal" -> "withdraw". An over-eager strip is harmless — the stem must
# still match an operation the design already exposes before anything fires.
_NOUN_SUFFIXES = ("ment", "ance", "ence", "al")


def _op_stem(word):
    """The verb stem of an operation noun ("withdrawals" -> "withdraw")."""
    stem = (word or "").lower()
    if stem.endswith("s"):
        stem = stem[:-1]
    for suf in _NOUN_SUFFIXES:
        if stem.endswith(suf) and len(stem) > len(suf) + 2:
            return stem[: -len(suf)]
    return stem


def _numeric_fields(entities_by_class):
    """{field_name: (class, declared_type)} for every numeric scalar column."""
    out = {}
    for cls, ent in (entities_by_class or {}).items():
        if not isinstance(ent, dict):
            continue
        for f in ent.get("fields") or []:
            if not isinstance(f, dict) or not isinstance(f.get("name"), str):
                continue
            if f["name"] == "id" or f["name"].endswith("_id"):
                continue
            if f.get("type") in ("int", "float"):
                out.setdefault(f["name"], (cls, f["type"]))
    return out


def _names_its_own_amount(op, prompt_text):
    """True when the specification already names a parameter for ``op``.

    The prompt's own signature ``restock(id, qty)`` (or a CLI line
    ``product restock --id --qty``) fixes the amount as the caller's value, so
    no implicit ``amount`` may be synthesised for it. Only a parameter beyond
    the row id counts — ``restock(id)`` alone still leaves the amount unnamed.
    """
    op = op.lower()
    for m in re.finditer(r"\b%s\s*\(([^)]*)\)" % re.escape(op), prompt_text or ""):
        params = [p.strip() for p in m.group(1).split(",") if p.strip()]
        if len(params) >= 2:
            return True
    # A CLI line the specification enumerates: "<group> <op> --id --qty".
    for line in (prompt_text or "").splitlines():
        low = line.lower()
        if re.search(r"\b%s\b" % re.escape(op), low):
            flags = re.findall(r"--([a-z_]+)", low)
            if len([f for f in flags if f not in ("id", "help")]) >= 1:
                return True
    return False


def extract_amount_ops(prompt_text, entities_by_class):
    """{class: {"field": <field>, "ops": [ {name, sign, amount_param,
    non_negative} ]}} for every delta operation the specification states.

    An operation is kept only when the prompt states a delta on a NUMERIC field
    of a designed entity AND does not already name a parameter for that
    operation. The optional ``non_negative`` flag comes from the prompt's own
    refusal sentence ("A withdrawal must be rejected if it would make the
    balance negative"), and is set only on the DECREASING operation.
    """
    text = prompt_text or ""
    if not text:
        return {}
    numeric = _numeric_fields(entities_by_class)
    if not numeric:
        return {}
    last_field = None
    found = {}  # cls -> {field, ops}
    for m in _DELTA_RE.finditer(text):
        op = _op_stem(m.group("op"))
        sign = _SIGN.get(m.group("dir").lower())
        obj = m.group("obj").lower()
        # "withdrawals decrease it" — "it" is the field the previous clause
        # named; an operation phrased that way is not a new subject.
        field = last_field if obj in ("it", "them") else obj
        if field is None or field not in numeric:
            continue
        last_field = field
        cls, _ftype = numeric[field]
        if _names_its_own_amount(op, text):
            continue
        bucket = found.setdefault(cls, {"field": field, "ops": []})
        if bucket["field"] != field:
            # Two different numeric fields in one entity is ambiguous: the
            # delta target must be unambiguous for the arithmetic to be right.
            continue
        entry = {
            "name": op,
            "sign": sign,
            "amount_param": _AMOUNT_PARAM,
            "non_negative": False,
        }
        if entry not in bucket["ops"]:
            bucket["ops"].append(entry)
    if not found:
        return {}
    # The refusal sentence marks the DECREASING operation(s) only.
    for m in _NEGATIVE_RE.finditer(text):
        op = _op_stem(m.group("op"))
        field = m.group("field").lower()
        cls = numeric.get(field, (None, None))[0]
        bucket = found.get(cls)
        if bucket is None or bucket["field"] != field:
            continue
        for entry in bucket["ops"]:
            if entry["name"] == op and entry["sign"] < 0:
                entry["non_negative"] = True
    return {
        cls: bucket for cls, bucket in found.items()
        if any(e["sign"] is not None for e in bucket["ops"])
    }
