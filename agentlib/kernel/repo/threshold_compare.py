"""Repository recipe: "rows below their referenced row's threshold".

The specification states the capability in prose only — "find low-stock
products (stock_qty below reorder_threshold)", where the threshold lives on
the REFERENCED entity (a product's category carries reorder_threshold). No
single-table recipe can express it, so the method shipped as ``return []``
(honest empty set) and the CLI command behind it listed nothing even when the
condition held.

The shape is structural, never domain vocabulary:

  * the method takes NO parameter and declares a list of its own entity;
  * its entity carries exactly one foreign key and, among its numeric non-FK
    columns, exactly ONE the method name points at (``stock`` in both
    ``stock_qty`` and ``find_low_stock_products``) — the value compared;
  * the REFERENCED entity carries exactly one numeric non-FK column, and that
    column is OPTIONAL (nullable or spec-defaulted) — an optional numeric
    neighbour is a threshold, not a second measure;
  * the method's NAME also carries one of the closed "below" words, which
    fixes the comparison direction.

Everything else returns None, so the method keeps its LLM fill.
"""
from ...naming import _camel, _entity_table_name, _snake

# The closed vocabulary that states the comparison direction: the named
# column is BELOW the referenced threshold. Kept as constants so the words
# live in one place; a name carrying none of them never takes this recipe.
_BELOW_WORDS = (
    "low", "below", "under", "insufficient", "lacking", "depleted",
    "short", "out", "manque", "bas", "faible", "sous",
)

# Suffixes a column name may carry that are NOT part of its meaning.
_COL_NOISE = ("_qty", "_count", "_cpt", "_total", "_amount", "_cents", "_id")


def _col_tokens(col):
    """Meaningful tokens of a column name (``stock_qty`` -> {"stock"})."""
    name = col
    for suffix in _COL_NOISE:
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return {t for t in name.split("_") if t}


def _numeric_cols(ent):
    """The entity's numeric non-FK column names, in declaration order."""
    return [
        f["name"] for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
        and f.get("type") in ("int", "float")
        and f["name"] != "id" and not f["name"].endswith("_id")
    ]


def _named_value_col(ent, name_tokens):
    """The ONE numeric column the method name points at, or None.

    An entity legitimately carries several numeric columns (a product has
    both ``price_cents`` and ``stock_qty``), so "the single numeric column"
    is not a shape. The method NAME is the discriminator: ``find_low_stock_
    products`` mentions ``stock``, which belongs to ``stock_qty`` and to no
    other numeric column. Ambiguity (two matches) or no match means the
    recipe must not guess.
    """
    matches = [
        c for c in _numeric_cols(ent)
        if _col_tokens(c) & name_tokens
    ]
    return matches[0] if len(matches) == 1 else None


def _single_fk(ent):
    """The entity's single foreign-key field name, or None."""
    fks = [
        f["name"] for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
        and f["name"].endswith("_id") and f["name"] != "id"
    ]
    return fks[0] if len(fks) == 1 else None


def _ref_threshold_col(ref):
    """The referenced entity's single OPTIONAL numeric column, or None.

    An optional numeric neighbour is a threshold, not a second measure: a
    required numeric column would be a value the spec could not leave unset,
    and two of them would be ambiguous.
    """
    nums = [
        f for f in (ref.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
        and f.get("type") in ("int", "float") and f["name"] != "id"
        and not f["name"].endswith("_id")
        and (f.get("nullable") or f.get("default") is not None)
    ]
    return nums[0]["name"] if len(nums) == 1 else None


def _threshold_compare_body(m, ent, model, params, returns,
                            entities_by_class):
    """Body lines for a "below the referenced threshold" list, or None."""
    if params or not entities_by_class:
        return None
    ret = (returns or "").strip()
    ret_l = ret.lower()
    squashed = ret_l.replace(" ", "")
    if not (
        (model in ret and ("list[" in ret_l or "list[" in squashed))
        or ret_l == "list"
        or squashed.startswith("list[dict")
        or squashed.startswith("list[list")
    ):
        return None
    name = _snake(m.get("name") or "")
    if not any(w in name for w in _BELOW_WORDS):
        return None
    value_col = _named_value_col(ent, _col_tokens(name))
    fk_col = _single_fk(ent)
    if not value_col or not fk_col:
        return None
    ref = entities_by_class.get(_camel(fk_col[: -len("_id")]))
    if not isinstance(ref, dict):
        return None
    threshold_col = _ref_threshold_col(ref)
    if not threshold_col:
        return None
    table = _entity_table_name(ent)
    ref_table = _entity_table_name(ref)
    return [
        "        with self.db.connect() as conn:",
        "            rows = conn.execute(",
        "                \"SELECT t.* FROM %s t JOIN %s r ON t.%s = r.id \""
        % (table, ref_table, fk_col),
        "                \"WHERE r.%s IS NOT NULL AND t.%s < r.%s\","
        % (threshold_col, value_col, threshold_col),
        "            ).fetchall()",
            "            return [%s(**dict(r)) for r in rows]" % model,
    ]


def _flag_threshold_spec(param, param_type, ent, entities_by_class,
                         declared_column=None):
    """Resolve a BOOLEAN list-filter param to a referenced-threshold test.

    ``list_products(category_id, low_only)`` means "optionally only
    low-stock ones", i.e. the rows whose compared column sits BELOW their
    referenced row's threshold. A design often records that intent as an
    ordinary bound filter (``low_only`` -> ``stock_qty <= ?``), which is
    doubly wrong: the click flag defaults to ``False``, and "is not None"
    then BINDS that ``False`` — ``AND stock_qty <= 0`` — so the unfiltered
    ``product list`` returned nothing at all.

    A bool param is never a bound value, so this resolves it back to the
    comparison it means. Returns ``{column, ref, ref_column}`` — the value
    column, the FK column and the referenced threshold column — or None,
    in which case the caller falls back to a constant-predicate floor.
    """
    # The type is vetted by the caller (``_is_bool_param_type``), which accepts
    # every bool spelling a design may use; a second, stricter check here would
    # silently defeat it for ``Boolean`` / ``Optional[bool] = None``.
    if not param_type:
        return None
    name = _snake(param or "")
    if not any(w in name for w in _BELOW_WORDS):
        return None
    value_col = _named_value_col(ent, _col_tokens(name))
    if not value_col and declared_column:
        # The param name need not mention the compared column: the DESIGN
        # already declared it (``low_only`` -> the ``stock_qty`` filter it was
        # recorded against). A numeric non-FK column of this entity is the
        # value being compared, exactly as in the name-derived case, so the
        # flag resolves to the threshold test it means instead of degrading to
        # a constant predicate on that column (inventory shipped
        # ``AND stock_qty > 0`` — "in stock", not "low stock").
        if declared_column in _numeric_cols(ent):
            value_col = declared_column
    fk_col = _single_fk(ent)
    if not value_col or not fk_col:
        return None
    ref_cls = _camel(fk_col[: -len("_id")])
    ref = (entities_by_class or {}).get(ref_cls)
    if not isinstance(ref, dict):
        return None
    threshold_col = _ref_threshold_col(ref)
    if not threshold_col:
        return None
    return {
        "column": value_col,
        "ref": fk_col,
        "ref_column": threshold_col,
        "ref_cls": ref_cls,
    }
