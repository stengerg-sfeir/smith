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
    if kind == "export_csv":
        if (
            returns and returns != "None"
            and "str" not in returns and "Path" not in returns
        ):
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
