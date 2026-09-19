"""Shared helpers for service kernel recipes.

Extracted from agent.py. These compute declared list() filter metadata and
cross-check a designed `impl` object against the designed entities so recipe
functions can stay small and independently registered.
"""
from ...naming import _camel, _snake


def _declared_filters(ent):
    """[(param, column, op)] exactly as the entity design declared them.

    The repository's list() API is built from this declaration alone — no
    suffix conventions, no field-name heuristics anywhere.
    """
    out = []
    for spec in ent.get("list_filters") or []:
        if (
            isinstance(spec, dict)
            and isinstance(spec.get("param"), str) and spec["param"]
            and isinstance(spec.get("column"), str) and spec["column"]
        ):
            out.append((spec["param"], spec["column"], spec.get("op", "eq")))
    return out


def _filter_params(ent):
    """Declared list() filter parameter names, in declaration order."""
    return [p for p, _, _ in _declared_filters(ent)]


def _filter_flag_refs(ent):
    """{param: {ref, ref_column, ref_cls}} for cross-table flag filters.

    A declared filter whose op is ``below_ref`` (see
    ``agentlib.kernel.repo.threshold_compare``) compares this entity's own
    column against a threshold column on the entity its foreign key points
    at, so the rendered ``list()`` needs a JOIN for it: ``ref`` is the FK
    column, ``ref_column`` the referenced threshold and ``ref_cls`` the
    referenced entity class.
    """
    out = {}
    for spec in ent.get("list_filters") or []:
        if not isinstance(spec, dict) or not spec.get("param"):
            continue
        if spec.get("op") != "below_ref":
            continue
        ref = spec.get("ref")
        ref_column = spec.get("ref_column")
        ref_cls = spec.get("ref_cls")
        if ref and ref_column and ref_cls:
            out[spec["param"]] = {
                "ref": ref,
                "ref_column": ref_column,
                "ref_cls": ref_cls,
            }
    return out


def _csv_chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def _impl_bindings_ok(impl, m, entities_by_class):
    """Cross-check an impl's references against the DESIGNED entities.

    Returns (class_name, ent_design) when every binding resolves against an
    existing entity and the method's own params; otherwise (None, None) so
    the caller degrades to CRUD delegation / a locked stub deterministically.
    """
    kind = impl.get("kind")
    returns = m.get("returns") or ""
    if kind == "contract_effects":
        # A prompt-derived contract render (see
        # agentlib.pipeline.method_contract): the impl is self-describing —
        # an anchor entity plus resolved effects. Validated here so a
        # contract can never reference an entity or a field the design does
        # not have. A bool-returning workflow is the whole point, so the
        # Dict/int return gate below must NOT apply.
        anchor = entities_by_class.get(_camel(impl.get("entity") or ""))
        if not isinstance(anchor, dict):
            return None, None
        anchor_fields = {
            f.get("name") for f in (anchor.get("fields") or [])
            if isinstance(f, dict)
        }
        effects = impl.get("effects") or []
        if not effects:
            return None, None
        if impl.get("id_param") not in [
            p.get("name") for p in (m.get("params") or [])
            if isinstance(p, dict)
        ]:
            return None, None
        for eff in effects:
            ref = entities_by_class.get(_camel(eff.get("cls") or ""))
            if not isinstance(ref, dict) or eff.get("field") not in {
                f.get("name") for f in (ref.get("fields") or [])
                if isinstance(f, dict)
            }:
                return None, None
            target = eff.get("target")
            if target != "self" and target not in anchor_fields:
                return None, None
        return _camel(impl["entity"]), anchor
    if kind == "create_child_row":
        # A prompt-derived INSERT workflow (see
        # agentlib.pipeline.method_contract): an anchor row loaded and
        # counter-moved, plus a CHILD row inserted. Validated here so the
        # renderer can never reference an entity, a column or a method
        # parameter the design does not have.
        anchor = entities_by_class.get(_camel(impl.get("entity") or ""))
        child = entities_by_class.get(_camel(impl.get("child") or ""))
        if not isinstance(anchor, dict) or not isinstance(child, dict):
            return None, None
        pnames = {
            p.get("name") for p in (m.get("params") or [])
            if isinstance(p, dict) and p.get("name")
        }
        if (impl.get("id_param") or "") not in pnames:
            return None, None
        anchor_fields = {
            f.get("name") for f in (anchor.get("fields") or [])
            if isinstance(f, dict)
        }
        for eff in impl.get("effects") or []:
            ref = entities_by_class.get(_camel(eff.get("cls") or ""))
            if not isinstance(ref, dict):
                return None, None
            if eff.get("field") not in {
                f.get("name") for f in (ref.get("fields") or [])
                if isinstance(f, dict)
            }:
                return None, None
            target = eff.get("target")
            if target != "self" and target not in anchor_fields:
                return None, None
        child_fields = {
            f.get("name") for f in (child.get("fields") or [])
            if isinstance(f, dict)
        }
        for spec in impl.get("child_fields") or []:
            if not isinstance(spec, dict) or spec.get("name") not in child_fields:
                return None, None
            if spec.get("param") and spec["param"] not in pnames:
                return None, None
        return _camel(impl["entity"]), anchor
    if kind == "report_parts":
        # A prompt-derived report render (see
        # agentlib.pipeline.method_contract): a COMPOUND report whose parts the
        # specification names ("total spent, per-category breakdown, budget
        # status"). Validated here so the impl can never name a field, a
        # grouping column or a period parameter the design does not have. The
        # period parameter must be one of the METHOD's own params — a report
        # that does not read its window is exactly the S1 defect.
        if not ("Dict" in returns or "dict" in returns):
            return None, None
        ent = entities_by_class.get(_camel(impl.get("entity") or ""))
        if not isinstance(ent, dict):
            return None, None
        fields = {
            f.get("name") for f in (ent.get("fields") or [])
            if isinstance(f, dict)
        }
        params = [
            p.get("name") for p in (m.get("params") or [])
            if isinstance(p, dict)
        ]
        if impl.get("value_field") not in fields:
            return None, None
        if impl.get("date_field") not in fields:
            return None, None
        if impl.get("period_param") not in params:
            return None, None
        if not impl.get("parts"):
            return None, None
        group = impl.get("group_field")
        if group and group not in fields:
            return None, None
        return _camel(impl["entity"]), ent
    if kind == "export_csv":
        # An export WRITES A FILE: its return is None, or a str/Path naming
        # what it wrote — never a container. The original substring test
        # (`"str" not in returns`) was defeated by the element type of a
        # container: `List[Dict[str, Any]]` SPELLS "str" inside `Dict[str, ...]`,
        # so prompt 07's `search_book(term) -> List[Dict[str, Any]]` passed as
        # an export. Its rendered body opened a CSV file NAMED BY THE SEARCH
        # TERM (`open(term, "w")`), ignored the repository's own
        # `search_book(term)` query, and returned None — the search feature was
        # dead, and the CLI crashed on every call.
        #
        # Normalise the annotation, then judge the OUTER shape: a container
        # return is never an export; anything else must name str/Path.
        flat = "".join((returns or "").split()).lower()
        if flat and flat != "none":
            if flat.startswith(("list", "dict", "tuple", "set")):
                return None, None
            if "str" not in flat and "path" not in flat:
                return None, None
    elif kind == "below_foreign_threshold":
        if returns and "List" not in returns and "list" not in returns:
            return None, None
    else:
        has_dict = "Dict" in returns or "dict" in returns
        numeric = "int" in returns.lower() or "float" in returns.lower()
        if not has_dict and not numeric:
            return None, None
    name = impl.get("entity") or ""
    ent = entities_by_class.get(_camel(name))
    if not isinstance(ent, dict) and name.endswith("s"):
        ent = entities_by_class.get(_camel(name[:-1]))
    if not isinstance(ent, dict):
        return None, None
    fields = {
        f.get("name") for f in (ent.get("fields") or [])
        if isinstance(f, dict)
    }
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    field_keys = {
        "total_in_period": ("value_field", "date_field"),
        "total_filtered": ("value_field",),
        "export_csv": (),
        "duplicate_groups": (),
        "sum_by_group": ("value_field",),
        "count_by_group": (),
        "below_foreign_threshold": ("value_field", "fk_field"),
    }.get(kind)
    if field_keys is None:
        return None, None
    for key in field_keys:
        if impl.get(key) not in fields:
            return None, None
    param_keys = {
        "total_in_period": ("period_param",),
        "export_csv": ("file_param",),
    }
    for key in param_keys.get(kind, ()):
        if impl.get(key) not in params:
            return None, None
    gb = impl.get("group_by")
    if kind in ("duplicate_groups", "sum_by_group", "count_by_group"):
        if not isinstance(gb, list) or not gb or any(g not in fields for g in gb):
            return None, None
    if kind == "below_foreign_threshold":
        ref_ent = entities_by_class.get(_camel(impl["ref_entity"]))
        if not isinstance(ref_ent, dict):
            return None, None
        ref_fields = {
            f.get("name") for f in (ref_ent.get("fields") or [])
            if isinstance(f, dict)
        }
        if impl["ref_field"] not in ref_fields:
            return None, None
    return _camel(impl["entity"]), ent


def _service_kwargs(m, ent):
    """[p for p in the method's params that are declared list filters]."""
    declared = set(_filter_params(ent))
    return [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name") in declared
    ]


# Range-role prefixes: a designed param named ``from_date``/``to_date`` is a
# paraphrase of the entity's own ``start_<x>``/``end_<x>`` declared filters.
# Pairing is by ROLE (lower vs upper bound), never by spelling, so a service
# ``list_expenses(from_date, to_date)`` binds to the declared gte/lte filters
# instead of silently dropping the range.
_RANGE_ROLE_PREFIXES = (
    ("start_", "gte"),
    ("from_", "gte"),
    ("after_", "gte"),
    ("since_", "gte"),
    ("end_", "lte"),
    ("to_", "lte"),
    ("until_", "lte"),
    ("before_", "lte"),
)


def _range_role(param):
    """'gte'/'lte' when a param name denotes a date-range bound, else None."""
    for prefix, op in _RANGE_ROLE_PREFIXES:
        if param.startswith(prefix):
            return op
    return None


def _resolve_filter_args(m, ent):
    """Pair each designed method param with one declared ``list()`` filter.

    Returns ``([(filter_param, method_param)], [unresolved_param])``.

    Exact name equality pairs first. A param the declared names cannot serve
    is then paired by ROLE: a ``from_``/``start_``-style name binds a ``gte``
    filter, a ``to_``/``end_``-style name an ``lte`` one, preferring a filter
    over a date-typed column. Anything still unpaired is reported so a caller
    can DECLINE rather than emit a partial call that silently drops a filter.
    """
    declared = _declared_filters(ent)
    declared_names = {fp for fp, _, _ in declared}
    field_types = {
        f.get("name"): f.get("type")
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    }
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict) and p.get("name")
    ]

    resolved = []
    unresolved = []
    used_filters = set()
    done_params = set()

    for param in params:
        if param in declared_names:
            resolved.append((param, param))
            used_filters.add(param)
            done_params.add(param)

    for param in params:
        if param in done_params:
            continue
        role = _range_role(param)
        pick = None
        if role:
            cands = [
                (fp, col) for fp, col, op in declared
                if op == role and fp not in used_filters
            ]
            dated = [
                fp for fp, col in cands
                if field_types.get(col) in ("date", "datetime")
            ]
            pick = dated[0] if dated else (cands[0][0] if cands else None)
        if pick is None:
            unresolved.append(param)
        else:
            resolved.append((pick, param))
            used_filters.add(pick)

    # Follow the declared filter order so the emitted call reads in the
    # repository's own argument order.
    order = {fp: i for i, (fp, _, _) in enumerate(declared)}
    resolved.sort(key=lambda pair: order.get(pair[0], len(order)))
    return resolved, unresolved


# ---------------------------------------------------------------------------
# Missing-row reporting
# ---------------------------------------------------------------------------

def not_found_message(entity_cls, id_expr):
    """A python expression: the MESSAGE of a missing-row error.

    ``'<entity> %s not found' % (<id>,)``. The CLI reports an error as
    ``Error: <str(exc)>``, and every not-found raise carried the raw id as its
    only argument — the user read ``Error: 99``, which names nothing (which
    entity? which argument?). The message names the entity the DESIGN declared
    and the id the caller typed, so the error is exploitable instead of
    opaque. Every raise site builds it here, so the wording cannot drift.
    """
    return "'%s %%s not found' %% (%s,)" % (_snake(entity_cls or "row"), id_expr)


def not_found_exception(entity_cls, exception_names):
    """The DESIGNED exception to raise when an ``<entity_cls>`` row is missing.

    A method that loads a row and finds nothing must SAY so. The
    specification's own error contract is a list of custom exception classes
    ("Implement proper error handling with custom exception classes:
    CategoryNotFoundError, ExpenseNotFoundError, BudgetExceededException"), and
    a lookup miss returned a bare ``False`` instead — exit 0, no message, so a
    user could not tell "nothing to do" from "no such row": ``return loan
    --loan-id 999`` printed ``False`` and ``budget update --category-id 999``
    printed ``False``, both exiting 0.

    Resolution is by NAME against the classes the DESIGN declared, never
    against a hard-coded list and never against the prompt text:

    1. ``<Entity>NotFoundError`` (the canonical name);
    2. ``Invalid<Entity>IdError`` / ``<Entity>IdError`` — the shape a design
       uses for an id that names no row (library's ``InvalidLoanIdError``);
    3. a project-wide ``NotFoundError``.

    Returns "" when the design declared no exception for this entity; the
    caller then keeps its ``return False`` rather than INVENTING a class name
    the project does not define (a NameError at runtime would be a worse bug
    than the silent False it replaces).
    """
    names = set(exception_names or [])
    entity = entity_cls or ""
    for want in (
        "%sNotFoundError" % entity,
        "%sNotFoundException" % entity,
        "%sNotFound" % entity,
        "Invalid%sIdError" % entity,
        "%sIdError" % entity,
        "Invalid%sError" % entity,
    ):
        if want in names:
            return want
    for want in ("NotFoundError", "NotFoundException"):
        if want in names:
            return want
    return ""


def missing_row_guard(entity_cls, id_expr, exception_names, indent="        "):
    """The ``if row is None:`` guard lines for a lookup miss.

    ``raise <DesignedNotFound>(<id_expr>)`` when the design declared an
    exception for the entity, else ``return False``. One place decides, so
    every recipe that loads a row reports a miss the same way.
    """
    exc = not_found_exception(entity_cls, exception_names)
    if exc:
        return [
            indent + "if row is None:",
            indent + "    raise %s(%s)"
            % (exc, not_found_message(entity_cls, id_expr)),
        ]
    return [indent + "if row is None:", indent + "    return False"]


def fk_parent_check(parent_cls, param, parent_var, exception_names,
                    indent="        "):
    """Lines that verify an FK parent row exists before a lookup miss is
    reported as a no-op.

    A caller that names a parent which does not exist (``budget update
    --category-id 999``) must not be answered with ``False``: the referenced
    row is absent, which is the very condition the designed exception class
    describes. Rendered as an explicit ``is None`` test so it is correct
    whichever style the repository uses for its getter (the deterministic CRUD
    getter returns ``None``; a design may raise instead — the raise propagates
    and the outcome is identical). Returns ``[]`` when the parent's entity has
    no designed exception, so nothing is invented.
    """
    exc = not_found_exception(parent_cls, exception_names)
    if not exc:
        return []
    return [
        indent + "if self.%s_repo.get_by_id(%s) is None:" % (parent_var, param),
        indent + "    raise %s(%s)"
        % (exc, not_found_message(parent_cls, param)),
    ]


def fk_parent_guards(params, entities_by_class, exception_names,
                     indent="            "):
    """Guard lines for every FK parent named by a ``<entity>_id`` parameter.

    Used inside an ``if row is None:`` block: a lookup that found nothing must
    distinguish "the referenced parent does not exist" (a real error, named by
    the design's own exception class) from "the row itself is absent" (an
    honest no-op). ``budget update --category-id 999 --month 2024-01``
    answered a bare ``False`` with exit 0 — the category it names does not
    exist, which is exactly what ``CategoryNotFoundError`` is for.

    Only a parameter whose entity the design MODELS and for which the design
    declared a not-found exception produces a guard; anything else is left to
    the plain ``return False``, so no class name is ever invented.
    """
    lines = []
    for param in params or []:
        if not isinstance(param, str) or not param.endswith("_id"):
            continue
        if param == "id":
            continue
        parent_cls = _camel(param[: -len("_id")])
        if parent_cls not in (entities_by_class or {}):
            continue
        lines += fk_parent_check(
            parent_cls, param, _snake(parent_cls), exception_names, indent=indent
        )
    return lines
