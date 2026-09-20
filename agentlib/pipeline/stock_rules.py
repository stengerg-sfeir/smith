"""Spec-declared STOCK MOVEMENT: a line's creation moves a counter it points at.

"Customers can place orders containing products. A customer must not be able to
place an order if any product has insufficient stock. When an order is
successfully created, the corresponding stock quantities must be decreased."
(prompt 53) states three things nothing enforced: the order line is the thing
created, the stock is a counter on the product the line points at, and an
insufficient counter refuses the creation.

The rule is read from the prompt's own movement phrase and then BOUND to the
design structurally — never to vocabulary the renderer would have to guess:

* the LINE entity is the one the design built for the containment: an entity
  with a surrogate id that mentions TWO designed entities by foreign key;
* the MOVED entity is the referenced one that carries a numeric counter whose
  NAME says stock/inventory/copies/count/quantity;
* BOTH referenced entities must be NAMED by the prompt, because the containment
  the prompt states is what puts them in scope;
* the quantity is the line's own numeric field (quantity/qty/units/count).

No rule is produced unless every one of those holds, so nothing is invented and
a prompt that never mentions stock (or a line) is untouched.
"""
from __future__ import annotations

import re

from agentlib.naming import _camel, _plural, _snake

# The movement phrase, in either order: the counter word and the verb.
_MOVE_RE = re.compile(
    r"\b(?:quantit(?:y|ies)|stock|inventory|count|units?|copies)\b"
    r"[^.]{0,60}?"
    r"\b(decreas|deduct|reduc|subtract|lower|increas|restor|replenish)"
    r"\w*\b"
    r"|\b(decreas|deduct|reduc|subtract|lower|increas|restor|replenish)"
    r"\w*\b[^.]{0,60}?"
    r"\b(?:quantit(?:y|ies)|stock|inventory|count|units?|copies)\b",
    re.IGNORECASE,
)
_DOWN = ("decreas", "deduct", "reduc", "subtract", "lower")
# The refusal the specification states for an insufficient counter.
_INSUFFICIENT_RE = re.compile(
    r"\binsufficient\b|\bnot\s+enough\b|\bout\s+of\s+stock\b"
    r"|\bmust\s+not\s+be\s+able\b|\bcannot\s+be\s+(?:placed|created|sold)\b",
    re.IGNORECASE,
)
_STOCK_TOKENS = ("stock", "inventory", "copies", "count", "quantity", "qty", "units")
_QTY_TOKENS = ("quantity", "qty", "units", "count", "amount")
_NUMERIC = ("int", "float")

# The RETURN leg: "cancelling an order must restore its product quantities"
# (prompt 56), "Cancelling a confirmed order releases the reserved stock"
# (prompt 60). The operation is named by the first verb of the clause, and the
# movement verb confirms the direction.
_RESTORE_RE = re.compile(
    r"\b(cancel\w*|cancelling|return\w*|refund\w*|reject\w*|void\w*|"
    r"release\w*|restore\w*)\b"
    r"[^.]{0,80}?"
    r"\b(restor|releas|increas|replenish|refund|return|add(?:ed)?\s+back)"
    r"\w*\b",
    re.IGNORECASE,
)
# The operation verb of a clause, restricted to the operations that can carry a
# return (an arbitrary word is never taken for an operation name).
_OP_RE = re.compile(
    r"\b(cancel|return|refund|reject|void|release)\w*\b", re.IGNORECASE
)


def _names_entity(text_low, cls):
    snake = _snake(cls)
    for token in (snake, _plural(snake)):
        if token and re.search(r"\b%s\b" % re.escape(token), text_low):
            return True
    return False


def _numeric_field(ent, tokens, exclude=()):
    """The entity's FIRST numeric field whose name carries one of ``tokens``."""
    for f in (ent or {}).get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "")
        if not name or name in exclude or name == "id":
            continue
        if (f.get("type") or "") not in _NUMERIC:
            continue
        if any(tok in name for tok in tokens):
            return name
    return None


def _fk_refs(ent, entities_by_class):
    """{fk column: referenced class} for the entity's designed references."""
    out = {}
    for f in (ent or {}).get("fields") or []:
        if not isinstance(f, dict):
            continue
        name = str(f.get("name") or "")
        if not name.endswith("_id") or name == "id":
            continue
        ref = _camel(name[: -len("_id")])
        if ref in entities_by_class:
            out[name] = ref
    return out


def _sign(text):
    """-1 for a decrease, +1 for an increase/restore."""
    m = _MOVE_RE.search(text or "")
    if not m:
        return 0
    verb = (m.group(1) or m.group(2) or "").lower()
    return -1 if verb.startswith(_DOWN) else 1


def extract_stock_rules(prompt_text, entities_by_class):
    """{line_class: rule} for the stock movement the prompt states.

    Rule: {"cls_line", "line_snake", "cls_ref", "ref_snake", "stock_field",
    "qty_field", "fk_param", "sign", "refuse"}.
    """
    text = prompt_text or ""
    if not text or not entities_by_class:
        return {}
    if not _MOVE_RE.search(text):
        return {}
    sign = _sign(text)
    if not sign:
        return {}
    refuse = sign < 0 and bool(_INSUFFICIENT_RE.search(text))
    low = text.lower()
    rules = {}
    for cls, ent in entities_by_class.items():
        if not isinstance(ent, dict):
            continue
        if not any(
            isinstance(f, dict) and f.get("name") == "id"
            for f in (ent.get("fields") or [])
        ):
            continue  # a line carries its own data; a pure join carries none
        refs = _fk_refs(ent, entities_by_class)
        if len(refs) < 2:
            continue
        qty_field = _numeric_field(ent, _QTY_TOKENS)
        if not qty_field:
            continue
        for fk_param, ref_cls in sorted(refs.items()):
            ref_ent = entities_by_class[ref_cls]
            stock_field = _numeric_field(ref_ent, _STOCK_TOKENS, exclude=(qty_field,))
            if not stock_field:
                continue
            # Every entity the line points at must be NAMED by the prompt: the
            # containment the specification states is what puts them in scope.
            if not all(_names_entity(low, r) for r in refs.values()):
                continue
            others = [r for f, r in refs.items() if f != fk_param]
            # The FK that ties the line to its CONTAINER (order_id) — the one
            # the return path filters on. It is NOT the counter's own FK
            # (product_id), which is what reads the counter row.
            container_fk = next(
                (f for f, r in refs.items() if f != fk_param), None
            )
            rules[cls] = {
                "cls_line": cls,
                "line_snake": _snake(cls),
                "cls_ref": ref_cls,
                "ref_snake": _snake(ref_cls),
                "stock_field": stock_field,
                "qty_field": qty_field,
                "fk_param": fk_param,
                "sign": sign,
                "refuse": refuse,
                # The container the line lives in, and the operation that hands
                # the quantities BACK (only when the prompt states that move).
                "restore": _restore_rule(text, others, cls, container_fk,
                                         qty_field, refs, ref_cls, stock_field),
            }
            break
    return rules


def _restore_rule(text, containers, line_cls, line_fk, qty_field, refs,
                  ref_cls, stock_field):
    """The 'cancelling restores the quantities' operation, or None.

    Only produced when the prompt STATES the return AND names the container the
    lines hang from — the operation then moves the counter by each line's own
    quantity. Nothing is invented: without the clause, or without a container
    the prompt names, there is no rule.
    """
    m = _RESTORE_RE.search(text or "")
    if not m:
        return None
    op_m = _OP_RE.search(m.group(0))
    if not op_m:
        return None
    low = (text or "").lower()
    for container_cls in containers:
        if not _names_entity(low, container_cls):
            continue
        return {
            "cls_container": container_cls,
            "container_snake": _snake(container_cls),
            "cls_line": line_cls,
            "line_snake": _snake(line_cls),
            "line_fk": line_fk,
            # The line's OWN foreign key to the counter entity (product_id):
            # the return path reads the counter row THROUGH it.
            "line_ref_fk": next(
                (f for f, r in refs.items() if r == ref_cls), None
            ),
            "qty_field": qty_field,
            "cls_ref": ref_cls,
            "ref_snake": _snake(ref_cls),
            "stock_field": stock_field,
            "op": op_m.group(1).lower(),
        }
    return None
