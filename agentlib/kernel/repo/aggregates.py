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

    Fires only when the single param names no declared filter AND the entity
    declares exactly one bool column, so which column the flag selects is
    unambiguous. Returns body lines, or None.
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

    Emits ``SUM(<the one numeric column>)`` over that WHERE clause and keys
    the result by the method's first param. Returns body lines, or None.
    """
    if not params or len(num_cols) != 1:
        return None
    frag, binds = where(params)
    if frag is None:
        return None
    ncol = num_cols[0]
    cast = _cast_for(fields[ncol].get("type"))
    key = params[0]
    return [
        "        with self.db.connect() as conn:",
        "            row = conn.execute(",
        '                "SELECT COALESCE(SUM(%s), 0) AS v FROM %s%s",'
        % (ncol, table, frag),
        "                %s" % tup(binds),
        "            ).fetchone()",
        "            return {%r: %s(row[\"v\"])}" % (key, cast),
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
        c for c in fields if fields[c].get("type") in ("bool", "boolean")
    ]
    fk_cols = sorted(c for c in fields if c.endswith("_id") and c != "id")
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
):
    """Dispatch the extra recipes; None => let the existing tiers decide."""
    if not ent:
        return None
    field_names = list(fields)

    body = _detect_and_mark_body(
        model, table, fields, num_cols, params, name, is_list_model
    )
    if body is not None:
        return body

    if is_list_model and "list" in ret_l:
        ptype = _param_type(m, params[0]) if len(params) == 1 else None
        body = _flag_list_body(
            model, table, fields, lfmap, params, ptype, field_names
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
        table, fields, lfmap, params, ptype, num_cols, date_cols, tup
    )
    if body is not None:
        return body
    return _filtered_aggregate_body(
        table, fields, lfmap, params, num_cols, where, tup
    )
