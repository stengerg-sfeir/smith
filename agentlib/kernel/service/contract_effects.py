"""Service recipe: render a method's PROMPT-DERIVED contract effects.

Registered as a discoverable `RECIPES` list under the kernel service package.

Input `impl` (built by ``agentlib.pipeline.method_contract.compile_contract_impl``
from a contract extracted from the SPECIFICATION, never from the code):

    {"kind": "contract_effects", "entity": "<anchor snake>",
     "id_param": "loan_id",
     "effects": [{"kind": "counter_delta", "cls": "Book",
                  "field": "available_copies", "delta": 1,
                  "target": "book_id" | "self"}, ...]}

The anchor entity's row is loaded by ``id_param``; then each effect is
applied to its target -- the row itself ("self") or the row referenced by one
of the anchor's FK columns. ``update`` is the deterministic repository API
(``update(id, data)``), so no field is ever written through a raw SQL path
here.

Why this exists: a ``bool``-returning workflow method (return_book,
renew_membership, ...) carries its invariants in prose the spec states and a
4B fill ignores -- ``return_book`` never incremented ``available_copies``, and
``renew_membership`` never flipped ``is_active``. Those effects are exactly
renderable, so they are rendered here instead of being left to the fill.
"""
from ...naming import _snake
from ..recipe_types import Recipe


def _field_expr(recv, field, effect):
    """The value expression written for one effect, on receiver ``recv``."""
    kind = effect["kind"]
    if kind == "counter_delta":
        return "(%s.%s or 0) + %d" % (recv, field, effect["delta"])
    if kind == "flag_toggle":
        return "not %s.%s" % (recv, field)
    if kind in ("flag_set", "status_set"):
        return "%r" % effect["value"]
    if kind == "date_set":
        # "sets return_date": the specification names the FIELD, and a
        # workflow stamping a return/close/completion timestamp can only mean
        # the CURRENT time. Rendered with the same ISO-string convention the
        # rest of the generated code uses for date columns (`import datetime`
        # is part of the standard service header).
        return "datetime.datetime.now().isoformat()"
    return None


def _h_contract_effects(m, impl, ent, entities_by_class):
    """Load the anchor row, then apply the contract's effects."""
    anchor_var = _snake(impl["entity"])
    idp = impl["id_param"]
    lines = [
        "        row = self.%s_repo.get_by_id(%s)" % (anchor_var, idp),
        "        if row is None:",
        "            return False",
    ]
    for eff in impl.get("effects") or []:
        target = eff.get("target")
        field = eff.get("field")
        if not field or not target:
            return None
        if target == "self":
            expr = _field_expr("row", field, eff)
            if expr is None:
                return None
            lines.append(
                "        self.%s_repo.update(%s, {'%s': %s})"
                % (anchor_var, idp, field, expr)
            )
            continue
        expr = _field_expr("target", field, eff)
        if expr is None:
            return None
        ref_var = _snake(eff["cls"])
        lines.append(
            "        target = self.%s_repo.get_by_id(row.%s)" % (ref_var, target)
        )
        lines.append("        if target is not None:")
        lines.append(
            "            self.%s_repo.update(target.id, {'%s': %s})"
            % (ref_var, field, expr)
        )
    lines.append("        return True")
    return lines


RECIPES = [Recipe("contract_effects", 20, _h_contract_effects)]
