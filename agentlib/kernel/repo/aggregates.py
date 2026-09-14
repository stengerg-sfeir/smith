"""Extra deterministic repo-custom bodies: flag lists + period aggregates.

These three bounded, shape-driven recipes run immediately before the
"unsatisfiable discriminator" fallback in ``_repo_method_body``. Each keys
ONLY on the designed signature, the designed entity shape, and the declared
filters of THIS entity — no prompt text and no domain vocabulary.

They close three fill defects observed on the expenses / library_system
prompts:

* ``list_members(active_only) -> List[Member]`` hit the honest-empty rule and
  returned ``[]`` for every call (the flag names no designed field, yet the
  entity has exactly one bool column it obviously selects).
* ``get_monthly_report(month) -> Dict`` / ``get_yearly_summary(year) -> Dict``
  were LLM-filled with raw ``[Model(**dict(r)) for r in rows]`` — a list where
  the annotation promises a dict, and no aggregation at all.
* ``get_category_spending(category_id, start_date, end_date) -> Dict[str, int]``
  was filled with a JOIN against ``categories.name`` binding an int id.

``ent`` may be falsy; every recipe then declines.
"""
import re

from ...naming import _entity_table_name

# The status words and the boundary at which the middle state starts. The
# specification states the three STATES of a budget status
# ("on_track/warning/exceeded") but never the boundary, so ONE documented
# default is used in the kernel while a service contract may override the
# words. Keeping a single convention means the repository's status and the
# report's per-category status can never disagree.
_WARN_RATIO = 0.8
_DEFAULT_LABELS = {"ok": "on_track", "warn": "warning", "over": "exceeded"}


def _param_type(m, pname):
    """Declared type of a designed param, or None when untyped/absent."""
    for p in m.get("params") or []:
        if isinstance(p, dict) and p.get("name") == pname:
            return p.get("type")
    return None


def _cast_for(col_type):
    """int/float coercion matching the column's declared storage type."""
    return "float" if col_type == "float" else "int"


def _flag_list_body(
    model, table, fields, lfmap, params, ptype, field_names
):
    """``List[<This>](<flag: bool>)`` -> WHERE <the one bool column> = ?.

    Fires only when the single param names no APPLIABLE declared filter (see
    ``_repo_extra_body``) AND the entity declares exactly one bool column, so
    which column the flag selects is unambiguous. Returns body lines, or None.
    """
    if len(params) != 1:
        return None
    pname = params[0]
    if pname in lfmap:
        return None
    if ptype not in ("bool", "boolean"):
        return None
    bool_cols = [
        n for n in field_names if fields[n].get("type") in ("bool", "boolean")
    ]
    if len(bool_cols) != 1:
        return None
    col = bool_cols[0]
    # A ``<x>_only`` parameter is a RESTRICTION, not a selector: the caller
    # asks for the rows that carry the flag, and OMITTING it means "no
    # restriction" — the specification's ``member list [--active-only]`` /
    # ``book list [--available-only]``. Emitting ``WHERE is_active = ?`` with
    # ``0`` for the omitted flag did the opposite: it listed exactly the
    # INACTIVE members and returned nothing at all for a fresh database,
    # while ``--active-only`` listed the active ones and no invocation could
    # list everything. The restriction form needs no bind, so the query is
    # assembled conditionally.
    if pname.endswith("_only"):
        return [
            "        with self.db.connect() as conn:",
            '            query = "SELECT * FROM %s WHERE 1=1"' % table,
            "            if %s:" % pname,
            '                query += " AND %s = 1"' % col,
            '            rows = conn.execute('
            'query + " ORDER BY id").fetchall()',
            "            return [%s(**dict(r)) for r in rows]" % model,
        ]
    # Any other bool parameter SELECTS the matching value (1/0).
    return [
        "        with self.db.connect() as conn:",
        "            rows = conn.execute(",
        '                "SELECT * FROM %s WHERE %s = ?",' % (table, col),
        "                (1 if %s else 0,)," % pname,
        "            ).fetchall()",
        "            return [%s(**dict(r)) for r in rows]" % model,
    ]


def _period_aggregate_body(
    table, fields, lfmap, params, ptype, num_cols, date_cols, tup
):
    """``Dict`` over ONE non-field scalar param -> SUM for that period bucket.

    The bucket width comes from the param's declared TYPE: an ``int`` year
    takes ``substr(<date>, 1, 4)``, anything else (a ``str`` "YYYY-MM") takes
    ``substr(<date>, 1, 7)``. Requires exactly one numeric and one date column
    so both the summed column and the bucket column are unambiguous.
    Returns body lines, or None.

    ``lfmap`` must hold only the APPLIABLE declared filters (see
    ``_repo_extra_body``): an entry naming no designed column, or one whose op
    the WHERE builder cannot render, is dropped from the rendered ``list()``
    anyway and must not shadow the aggregate.
    """
    if len(params) != 1 or len(num_cols) != 1 or len(date_cols) != 1:
        return None
    pname = params[0]
    if pname in lfmap or pname in fields:
        return None
    ncol, dcol = num_cols[0], date_cols[0]
    width = 4 if ptype == "int" else 7
    src = "str(%s)" % pname if ptype == "int" else pname
    cast = _cast_for(fields[ncol].get("type"))
    return [
        "        with self.db.connect() as conn:",
        "            row = conn.execute(",
        '                "SELECT COALESCE(SUM(%s), 0) AS total,'
        ' COUNT(*) AS n FROM %s WHERE substr(%s, 1, %d) = ?",'
        % (ncol, table, dcol, width),
        "                %s" % tup([src]),
        "            ).fetchone()",
        "            return {'total': %s(row[\"total\"]), 'count': int(row[\"n\"])}"
        % cast,
    ]


def _filtered_aggregate_body(
    table, fields, lfmap, params, num_cols, where, tup
):
    """``Dict`` over params that ALL resolve to declared filters -> SUM.

    Emits ``SUM(<the one numeric column>)`` over that WHERE clause and returns
    ``{'total': ..., 'count': ...}`` — the SAME key convention
    ``_period_aggregate_body`` already uses. Keying the aggregate by the
    method's first parameter was a defect (S3): ``get_category_spending(
    category_id, start_date, end_date)`` returned ``{'category_id': 3000}`` —
    the money total stored under the name of the category it was filtered BY,
    with no ``total`` key at all — and the service consuming it read
    ``total_spent``/``count`` and silently got ``None``. An aggregate is named
    by what it IS. Returns body lines, or None.
    """
    if not params or len(num_cols) != 1:
        return None
    frag, binds = where(params)
    if frag is None:
        return None
    ncol = num_cols[0]
    cast = _cast_for(fields[ncol].get("type"))
    return [
        "        with self.db.connect() as conn:",
        "            row = conn.execute(",
        '                "SELECT COALESCE(SUM(%s), 0) AS v,'
        ' COUNT(*) AS n FROM %s%s",' % (ncol, table, frag),
        "                %s" % tup(binds),
        "            ).fetchone()",
        "            return {'total': %s(row[\"v\"]), 'count': int(row[\"n\"])}"
        % cast,
    ]


def _budget_status_body(
    model, fields, params, ret_l, entities_by_class, num_cols, tup,
    warn_ratio, labels,
):
    """``str`` over ONE row id -> that row's limit vs ACTUAL spending.

    Shape-gated and design-only. The owner entity must carry exactly one
    foreign key (the group the budget is kept for), exactly one str column
    (the period, "YYYY-MM") and exactly one numeric non-FK column (the limit);
    exactly ONE other designed entity must carry that same foreign key plus
    exactly one date column and one numeric column — the spending compared.
    The status is then ``SUM(spending)`` for that (group, period) against the
    limit, in the three states the specification names.

    Why: expenses' ``BudgetRepository.check_budget_status(budget_id)``
    compared the budget's LIMIT to the category's ``monthly_budget`` FIELD —
    never to actual spending — and
    ``CategoryRepository.check_category_budget_status`` summed ALL TIME,
    ignoring the month (S7). Neither the limit nor the period was ever tied to
    what was spent. Returns body lines, or None.
    """
    if "str" not in ret_l or len(params) != 1:
        return None
    fks = sorted(
        f for f in fields
        if isinstance(f, str) and f.endswith("_id") and f != "id"
    )
    strs = [
        f for f in fields
        if isinstance(f, str) and fields[f].get("type") == "str"
    ]
    if len(fks) != 1 or len(strs) != 1 or len(num_cols) != 1:
        return None
    fk, period, limit = fks[0], strs[0], num_cols[0]
    spend = []
    for cls, other in (entities_by_class or {}).items():
        if cls == model or not isinstance(other, dict):
            continue
        ofields = {
            f.get("name"): f for f in (other.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        }
        if fk not in ofields:
            continue
        odates = [
            n for n, f in ofields.items()
            if f.get("type") in ("date", "datetime")
        ]
        onums = [
            n for n, f in ofields.items()
            if isinstance(n, str) and f.get("type") in ("int", "float")
            and n != "id" and not n.endswith("_id")
        ]
        if len(odates) == 1 and len(onums) == 1:
            spend.append((cls, odates[0], onums[0]))
    if len(spend) != 1:
        return None
    scls, sdate, snum = spend[0]
    stable = _entity_table_name(entities_by_class[scls])
    pid = params[0]
    return [
        "        with self.db.connect() as conn:",
        "            row = conn.execute(",
        '                "SELECT %s, %s, %s FROM %s WHERE id = ?",'
        % (fk, period, limit, _entity_table_name(entities_by_class[model])),
        "                %s" % tup([pid]),
        "            ).fetchone()",
        "            if row is None:",
        "                return 'unknown'",
        "            spent = conn.execute(",
        '                "SELECT COALESCE(SUM(%s), 0) AS v FROM %s'
        ' WHERE %s = ? AND substr(%s, 1, 7) = ?",'
        % (snum, stable, fk, sdate),
        "                %s" % tup(["row[%r]" % fk, "row[%r]" % period]),
        "            ).fetchone()[\"v\"]",
        "            limit = row[%r]" % limit,
        "            if spent > limit:",
        "                return %r" % labels["over"],
        "            if limit and spent >= limit * %s:" % warn_ratio,
        "                return %r" % labels["warn"],
        "            return %r" % labels["ok"],
    ]


def _detect_and_mark_body(
    model, table, fields, num_cols, params, name, is_list_model
):
    """``List[<This>]`` zero-param ``detect_/mark_/flag_<x>`` -> set the flag.

    A repo method named ``detect_``/``mark_``/``flag_``<something> that takes
    no params and returns the entity list is a "find duplicates and mark
    them" operation: the intent says detect recurring expenses AND mark them
    as recurring, but the LLM fill emitted a SELECT that only read rows
    ALREADY flagged (``WHERE <flag> = 1 AND EXISTS(...)``) and never set the
    flag — detect_recurring was a no-op on a fresh table.

    Deterministic and shape-gated: exactly ONE bool column (the flag) and
    exactly ONE numeric column (the "same value" discriminator) plus at
    least one FK column (the "same category" discriminator). Rows sharing
    both are flagged, then the flagged rows are returned. Anything else
    declines, so the method stays a stub for the LLM fill as before.
    """
    if not is_list_model or params:
        return None
    if not re.match(r"^(detect|mark|flag)_", name or ""):
        return None
    bool_cols = [
        c for c in fields
        if isinstance(c, str) and fields[c].get("type") in ("bool", "boolean")
    ]
    fk_cols = sorted(
        c for c in fields
        if isinstance(c, str) and c.endswith("_id") and c != "id"
    )
    if len(bool_cols) != 1 or len(num_cols) != 1 or not fk_cols:
        return None
    flag, num, fk = bool_cols[0], num_cols[0], fk_cols[0]
    return [
        "        with self.db.connect() as conn:",
        "            conn.execute(",
        '                "UPDATE %s SET %s = 1 WHERE id IN ("' % (table, flag),
        '                "    SELECT a.id FROM %s a JOIN %s b"' % (table, table),
        '                "      ON a.id != b.id AND a.%s = b.%s'
        ' AND a.%s = b.%s)"' % (num, num, fk, fk),
        "            )",
        "            conn.commit()",
        "            rows = conn.execute(",
        '                "SELECT * FROM %s WHERE %s = 1"' % (table, flag),
        "            ).fetchall()",
        '            return [%s(**dict(r)) for r in rows]' % model,
    ]


def _repo_extra_body(
    m,
    ent,
    model,
    name,
    params,
    ret_l,
    fields,
    table,
    lfmap,
    num_cols,
    date_cols,
    is_list_model,
    where,
    tup,
    is_row_list=False,
    entities_by_class=None,
):
    """Dispatch the extra recipes; None => let the existing tiers decide."""
    if not ent:
        return None
    field_names = list(fields)

    # A declared filter may shadow a recipe ONLY when it is APPLIABLE: its
    # column must resolve to a designed field AND its op must be one the
    # WHERE builder can render. A stale or hallucinated entry — a "month"
    # filter whose op ``_where`` cannot render, or whose column names no
    # designed field — is already dropped from the rendered ``list()``
    # signature, so it must not block a recipe either. It did:
    # expenses' ``get_monthly_report(month)`` declined the period aggregate
    # (mere membership in ``list_filters``) while its twin
    # ``get_yearly_summary(year)`` — no phantom entry — took it, and the
    # monthly report was LLM-filled with a raw row LIST under a Dict
    # annotation.
    filter_lfmap = {
        k: v for k, v in lfmap.items()
        if isinstance(v, dict)
        and v.get("column") in fields
        and where([k])[0] is not None
    }

    body = _budget_status_body(
        model, fields, params, ret_l, entities_by_class, num_cols, tup,
        _WARN_RATIO, _DEFAULT_LABELS,
    )
    if body is not None:
        return body

    # ``is_row_list`` too: the design annotates these repo methods
    # ``List[Dict[str, Any]]`` as often as ``List[<This>]``, and the recipe
    # used to require the ENTITY spelling — so expenses' repo
    # ``detect_recurring()`` missed it and the fill emitted an UNSATISFIABLE
    # WHERE (``substr(...) = substr(...) AND substr(...) > substr(...)``,
    # equal AND greater, so it could only ever return []).
    body = _detect_and_mark_body(
        model, table, fields, num_cols, params, name,
        is_list_model or is_row_list,
    )
    if body is not None:
        return body

    if is_list_model and "list" in ret_l:
        ptype = _param_type(m, params[0]) if len(params) == 1 else None
        body = _flag_list_body(
            model, table, fields, filter_lfmap, params, ptype, field_names
        )
        if body is not None:
            return body
        return None

    # A `List[Dict[...]]` return also contains "dict" — exclude it so only a
    # genuine dict result takes the aggregate recipes.
    if "dict" not in ret_l or "list" in ret_l:
        return None
    ptype = _param_type(m, params[0]) if len(params) == 1 else None
    body = _period_aggregate_body(
        table, fields, filter_lfmap, params, ptype, num_cols, date_cols, tup
    )
    if body is not None:
        return body
    # A design may type its period column as a plain ``str`` (the prompt's
    # own ``expense_date (str, ISO date)`` spells the storage type, not a
    # date object), which keeps it out of ``date_cols`` and left
    # ``get_monthly_report``/``get_yearly_summary`` to the LLM — which
    # answered with a raw row LIST where the annotation promises a dict, and
    # no aggregation at all. When NO column is declared date-typed, widen to
    # the single date-ISH NAMED column; the summed column is still required
    # to be unique, so what is aggregated stays unambiguous.
    if not date_cols:
        date_ish = [
            n for n in fields
            if isinstance(n, str) and (
                n.endswith("_date") or n.endswith("_at")
                or n in ("date", "month", "year")
            )
        ]
        if len(date_ish) == 1:
            body = _period_aggregate_body(
                table, fields, filter_lfmap, params, ptype, num_cols,
                date_ish, tup
            )
            if body is not None:
                return body
    return _filtered_aggregate_body(
        table, fields, lfmap, params, num_cols, where, tup
    )
