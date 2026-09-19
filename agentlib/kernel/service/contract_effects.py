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
from ...naming import _camel, _snake
from ..recipe_types import Recipe
from .common import missing_row_guard


def _non_negative_guard(field, effect, exception_names):
    """Refuse a delta that would drive ``field`` below zero.

    The specification states the refusal itself — "A withdrawal must be
    rejected if it would make the balance negative" (prompt 31) — and the
    design declares an exception for it. The class is chosen by the design's
    OWN naming (``InsufficientFundsError`` mentions neither the field nor the
    rule, so the search is deliberately broad: funds/balance/negative first,
    then the generic validation names, then the builtin ``ValueError``), never
    from domain vocabulary in the renderer.
    """
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    exc = None
    for want in ("insufficient", "fund", "balance", "negative",
                 "invalid", "validation", "value"):
        for name in sorted(names):
            if want in name.lower():
                exc = name
                break
        if exc:
            break
    if exc is None:
        exc = "ValueError"
    param = effect["param"]
    return [
        "        if (row.%s or 0) < float(%s if %s is not None else 0):"
        % (field, param, param),
        "            raise %s(%r)" % (exc, "%s would become negative" % field),
    ]


def _field_expr(recv, field, effect):
    """The value expression written for one effect, on receiver ``recv``."""
    kind = effect["kind"]
    if kind == "counter_delta":
        return "(%s.%s or 0) + %d" % (recv, field, effect["delta"])
    if kind == "amount_delta":
        # The amount is the CALLER's own parameter (no literal in the
        # specification): "Deposits increase the balance and withdrawals
        # decrease it" names only the direction, so the value is `amount`,
        # signed by the operation. ``float()`` because the design types the
        # CLI's numeric options as text as often as not.
        param = effect["param"]
        return (
            "(%s.%s or 0) + (%s * float(%s if %s is not None else 0))"
            % (recv, field, effect["sign"], param, param)
        )
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


def _already_state_guard(impl, idp, exception_names):
    """The guard refusing an operation already in its TARGET state, or [].

    ``return_book`` sets ``status = 'returned'``, and the design declares
    ``LoanAlreadyReturnedError``. Nothing read the state first, so
    ``library return --loan-id 1`` run three times incremented
    ``available_copies`` 1 -> 2 -> 3 — the declared exception was unreachable
    and the counter drifted further from the truth at every call. The guard is
    built from the design's OWN two declarations (the status effect, which
    names the field and the value, and the exception class), never from domain
    vocabulary: an exception whose NAME contains "already" AND the value the
    effect writes is exactly the class that describes this refusal. No such
    class, no guard — nothing is invented.
    """
    names = [n for n in (exception_names or []) if isinstance(n, str)]
    for eff in impl.get("effects") or []:
        if eff.get("kind") != "status_set" or eff.get("target") != "self":
            continue
        field = eff.get("field")
        value = eff.get("value")
        # A three-letter value is the shortest that can identify a state
        # ("ok" is too generic to match an exception name against).
        if not field or not isinstance(value, str) or len(value) < 3:
            continue
        low_value = value.lower()
        for name in sorted(names):
            low = name.lower()
            if "already" in low and low_value in low:
                return [
                    "        if row.%s == %r:" % (field, value),
                    "            raise %s(%s)"
                    % (
                        name,
                        "'%s %%s is already %s' %% (%s,)"
                        % (_snake(impl["entity"]), value, idp),
                    ),
                ]
    return []


def _h_contract_effects(m, impl, ent, entities_by_class, exception_names=None):
    """Load the anchor row, then apply the contract's effects."""
    anchor_var = _snake(impl["entity"])
    idp = impl["id_param"]
    # The anchor row is identified by an id the caller typed: a miss is a
    # NOT-FOUND, not a silent False. `return loan --loan-id 999` used to print
    # `False` and exit 0, so a user could not distinguish "nothing to do" from
    # "no such loan"; the design's own exception class says which it is.
    lines = ["        row = self.%s_repo.get_by_id(%s)" % (anchor_var, idp)]
    # `impl["entity"]` is the snake name; the design's exception classes are
    # named after the CamelCase class (InvalidLoanIdError), so resolve through
    # _camel before looking a class up by name.
    lines += missing_row_guard(_camel(impl["entity"]), idp, exception_names)
    lines += _already_state_guard(impl, idp, exception_names)
    for eff in impl.get("effects") or []:
        target = eff.get("target")
        field = eff.get("field")
        if not field or not target:
            return None
        if target == "self":
            expr = _field_expr("row", field, eff)
            if expr is None:
                return None
            if eff.get("non_negative"):
                # The refusal is emitted BEFORE the update so nothing is
                # written when the operation would overdraw.
                lines += _non_negative_guard(field, eff, exception_names)
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
