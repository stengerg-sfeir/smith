"""Service recipe: render a workflow that INSERTS a row (and may move counters).

Registered as a discoverable `RECIPES` list under the kernel service package.

Input `impl` (built by
``agentlib.pipeline.method_contract.compile_contract_impl`` out of a contract
transcribed from the SPECIFICATION — either extracted by the analyst or read
literally from the method's own spec line):

    {"kind": "create_child_row",
     "entity": "book",            # the anchor row loaded and counter-moved
     "id_param": "book_id",       # the method parameter holding the anchor id
     "child": "Loan",             # the row inserted
     "child_fields": [{"name": "book_id", "param": "book_id"},
                      {"name": "loan_date", "now": True},
                      {"name": "status", "value": "active"}, ...],
     "effects": [{"kind": "counter_delta", "cls": "Book",
                  "field": "available_copies", "delta": -1, "target": "self"}],
     "guards": [{"kind": "reject_unavailable", "cls": "Book",
                 "field": "available_copies"}]}

Why this exists. ``compile_contract_impl`` deliberately left a ``create_child``
effect to the LLM fill ("inserting a child row needs required-field stamping").
The fill then shipped library_system's ``borrow_book`` as a dead
``return False`` stub: borrowing neither decremented the book nor created the
loan, and the executed oracle caught it ("borrow_book must decrement
available_copies to 1"). The stamping the comment worried about is exactly
derivable — every required column of the inserted row is named by one of the
method's own parameters, defaulted by the design, or a date the specification
leaves at "now" — so the whole operation is rendered here instead.

Nothing is invented: the anchor, the child, every column and every value come
from the contract, which is closed against the specification.
"""
from ...naming import _camel, _snake
from ..recipe_types import Recipe
from .common import fk_parent_check, missing_row_guard

# Exception-name families the DESIGN may have declared for a refused
# operation. Resolution is by name against the project's own classes, never
# against a hard-coded list of the generator's: a class the design did not
# declare is never referenced (which would be a NameError at runtime).
_UNAVAILABLE_TOKENS = ("notavailab", "unavailab", "outofstock", "nostock")
_INACTIVE_TOKENS = ("notactive", "inactive", "deactivated")


def _guard_exception(cls, exception_names, tokens):
    """The DESIGNED exception class for a refused operation, or ""."""
    names = set(exception_names or [])
    # Canonical shapes first: <Entity>NotAvailableError / <Entity>InactiveError.
    for suffix in ("NotAvailableError", "UnavailableError", "NotActiveError",
                   "InactiveError", "AlreadyExistsError", "DuplicateError"):
        want = "%s%s" % (cls or "", suffix)
        if want in names:
            return want
    for token in tokens:
        for name in sorted(names):
            if token in name.lower():
                return name
    return ""


def _id_expr_for(cls, impl, idp):
    """The method parameter holding ``cls``'s id.

    The anchor's own id for the anchor entity, otherwise the child column that
    references ``cls`` — so a refusal names the id the caller actually typed
    (``borrow --member-id 9 --book-id 1`` refusing the MEMBER must quote 9, not
    1).
    """
    if cls and _snake(cls) == _snake(impl.get("entity") or ""):
        return idp
    for spec in impl.get("child_fields") or []:
        if not isinstance(spec, dict):
            continue
        if cls and spec.get("name") == _snake(cls) + "_id" and spec.get("param"):
            return spec["param"]
    return idp


def _child_fk_guards(impl, idp, entities_by_class, exception_names):
    """Existence guards for the child row's parameter-filled FOREIGN KEYS.

    `borrow_book` inserts a Loan whose `member_id` comes straight from the
    caller. Nothing verified that member, so `library borrow --member-id 999
    --book-id 1` reached the INSERT and aborted with a raw
    `sqlite3.IntegrityError: FOREIGN KEY constraint failed`, which the CLI
    printed to the user verbatim. The design declares `InvalidMemberIdError`
    for exactly this; the guard renders it. The anchor's own id is skipped —
    its row was loaded (and guarded) by the caller — and a class the design
    models without a not-found exception yields no guard at all, so nothing is
    ever invented.
    """
    lines = []
    emitted = set()
    for spec in impl.get("child_fields") or []:
        if not isinstance(spec, dict):
            continue
        param = spec.get("param")
        if not isinstance(param, str) or not param.endswith("_id"):
            continue
        if param == idp or param == "id" or param in emitted:
            continue
        parent_cls = _camel(param[: -len("_id")])
        if parent_cls not in (entities_by_class or {}):
            continue
        emitted.add(param)
        lines += fk_parent_check(
            parent_cls, param, _snake(parent_cls), exception_names
        )
    return lines


def _counter_lines(impl, idp, indent="        "):
    """Apply every counter effect to the anchor row's own columns."""
    lines = []
    for eff in impl.get("effects") or []:
        if eff.get("kind") != "counter_delta" or eff.get("target") != "self":
            continue
        field = eff.get("field")
        delta = eff.get("delta")
        if not field or not delta:
            continue
        if delta < 0:
            expr = "(row.%s or 0) - %d" % (field, -delta)
        else:
            expr = "(row.%s or 0) + %d" % (field, delta)
        lines.append(
            "%sself.%s_repo.update(%s, {'%s': %s})"
            % (indent, _snake(impl["entity"]), idp, field, expr)
        )
    return lines


def _guard_lines(impl, idp, exception_names, returns_bool, indent="        "):
    """The refusal checks the specification states, or None to decline.

    A guard whose exception the design never declared is rendered as
    ``return False`` when the method returns a bool — the design's own
    annotation says a refusal IS a bool result — and otherwise DECLINES the
    render, so a half-guarded workflow keeps its LLM fill.
    """
    lines = []
    for guard in impl.get("guards") or []:
        kind = guard.get("kind")
        field = guard.get("field") or ""
        cls = guard.get("cls") or ""
        if kind == "reject_unavailable":
            exc = _guard_exception(cls, exception_names, _UNAVAILABLE_TOKENS)
            cond = "(row.%s or 0) <= 0" % field
        elif kind == "reject_inactive":
            exc = _guard_exception(cls, exception_names, _INACTIVE_TOKENS)
            cond = "not row.%s" % field
        else:
            # A duplicate is already refused by the schema's UNIQUE
            # constraint; rendering it here would need a lookup shape the
            # specification does not state.
            return None
        if not field:
            return None
        lines.append("%sif %s:" % (indent, cond))
        if exc:
            _idv = _id_expr_for(cls, impl, idp)
            _word = "is not active" if kind == "reject_inactive" else "is not available"
            lines.append(
                "%s    raise %s(%s)"
                % (
                    indent,
                    exc,
                    "'%s %%s %s' %% (%s,)"
                    % (_snake(cls or impl.get("entity") or "row"), _word, _idv),
                )
            )
            del _idv, _word
        elif returns_bool:
            lines.append("%s    return False" % indent)
        else:
            return None
    return lines


def _child_lines(impl, indent="        "):
    """Insert the child row with every required column stamped."""
    child = impl.get("child") or ""
    if not child:
        return []
    kwargs = []
    for spec in impl.get("child_fields") or []:
        name = spec.get("name")
        if not name:
            return []
        if spec.get("param"):
            kwargs.append("%s=%s" % (name, spec["param"]))
        elif "value" in spec:
            kwargs.append("%s=%r" % (name, spec["value"]))
        elif spec.get("now"):
            kwargs.append(
                "%s=datetime.datetime.now().isoformat()" % name
            )
        else:
            return []
    var = _snake(child)
    return [
        "%s%s = %s(%s)" % (indent, var, child, ", ".join(kwargs)),
        "%sself.%s_repo.create(%s)" % (indent, var, var),
    ]


def _h_create_child_row(m, impl, ent, entities_by_class,
                        exception_names=None):
    """Load the anchor row, run the guards, move the counters, insert."""
    idp = impl.get("id_param") or ""
    if not idp:
        return None
    anchor_var = _snake(impl["entity"])
    lines = ["        row = self.%s_repo.get_by_id(%s)" % (anchor_var, idp)]
    lines += missing_row_guard(_camel(impl["entity"]), idp, exception_names)
    lines += _child_fk_guards(impl, idp, entities_by_class, exception_names)
    ret = (m.get("returns") or "").strip().lower()
    returns_bool = (not ret) or "bool" in ret
    guard_lines = _guard_lines(impl, idp, exception_names, returns_bool)
    if guard_lines is None:
        return None
    lines += guard_lines
    lines += _counter_lines(impl, idp)
    child_lines = _child_lines(impl)
    if child_lines is None:
        return None
    if not child_lines:
        return None
    lines += child_lines
    lines.append("        return True")
    return lines


RECIPES = [Recipe("create_child_row", 15, _h_create_child_row)]
