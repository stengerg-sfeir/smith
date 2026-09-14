"""Repository recipe: a "has this limit been exceeded" STATUS method.

The specification states the capability in prose only — "check if a category
has exceeded its budget" — so neither the method name nor its return type is
fixed by the prompt. The DESIGN fixes both, and this recipe renders the body
from the designed SHAPE alone (no domain vocabulary):

  * the method DECLARES a ``str`` (a status word, not rows);
  * its repository's entity carries exactly one foreign key, exactly one
    numeric non-FK column (the LIMIT) and exactly one str column (the PERIOD);
  * exactly ONE other designed entity shares that foreign key and carries
    exactly one date/datetime and exactly one numeric non-FK column — the
    substance being spent.

Rendered behaviour: read the limit row for the requested period, sum the
spending of the shared entity over the same period (raw SQL: a repository
holds ``self.db``, never another repository), and return the specification's
own status vocabulary.

Why it exists: ``BudgetRepository.check_budget_exceeded -> str`` shipped
``return self.list(category_id=..., month=...)`` — a ``List[Budget]`` under a
``str`` annotation, so the capability the specification requires returned no
verdict at all and any caller reading a status crashed or silently mis-read.
Any shape mismatch returns None, so the method keeps its LLM fill.
"""
from ...naming import _entity_table_name, _snake
from ..service.common import _filter_params

# The vocabulary the specification uses for the same comparison in the
# monthly report ("budget status (on_track/warning/exceeded)"). Kept as
# constants so the labels live in one place.
STATUS_OK = "on_track"
STATUS_WARN = "warning"
STATUS_OVER = "exceeded"

# Fraction of the limit at which the status turns to "warning" (nine tenths,
# expressed in integer arithmetic so no float ever enters a money path).
_WARN_RATIO_NUM = 9
_WARN_RATIO_DEN = 10


def _period_and_fk(ent, params):
    """(fk_param, fk_col, period_param, period_col) for the limit entity.

    Design-only: the parameter must be one the entity's own ``list()``
    accepts (``_filter_params``) and must map to a declared filter column.
    """
    pairs = {}
    for spec in (ent.get("list_filters") or []):
        if not isinstance(spec, dict):
            continue
        param = spec.get("param")
        col = spec.get("column")
        if isinstance(param, str) and param and isinstance(col, str) and col:
            pairs[param] = col
    accepted = set(_filter_params(ent))
    fk_param = next(
        (p for p in params if p in accepted and pairs.get(p, "").endswith("_id")),
        None,
    )
    period_param = next(
        (p for p in params if p in accepted and not pairs.get(p, "").endswith("_id")),
        None,
    )
    if not fk_param or not period_param:
        return None
    return fk_param, pairs[fk_param], period_param, pairs[period_param]


def _limit_fields(ent):
    """(limit_field, period_field, fk_field) of the limit entity, or None."""
    fields = [
        f for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    ]
    fks = [
        f["name"] for f in fields
        if f["name"].endswith("_id") and f["name"] != "id"
    ]
    nums = [
        f["name"] for f in fields
        if f.get("type") in ("int", "float") and f["name"] != "id"
        and not f["name"].endswith("_id")
    ]
    strs = [f["name"] for f in fields if f.get("type") == "str"]
    if len(fks) != 1 or len(nums) != 1 or len(strs) != 1:
        return None
    return nums[0], strs[0], fks[0]


def _spend_shape(entities_by_class, fk_field, limit_cls):
    """(table, amount_col, date_col, var) of the unique spending entity.

    "The substance being spent" is the one OTHER designed entity that shares
    the limit entity's foreign key and carries exactly one date/datetime
    column plus exactly one numeric non-FK column. Two candidates => None.
    """
    found = []
    for cls, ent in (entities_by_class or {}).items():
        if cls == limit_cls or not isinstance(ent, dict):
            continue
        fields = [
            f for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        ]
        if fk_field not in {f["name"] for f in fields}:
            continue
        dates = [
            f["name"] for f in fields
            if f.get("type") in ("date", "datetime")
        ]
        nums = [
            f["name"] for f in fields
            if f.get("type") in ("int", "float") and f["name"] != "id"
            and not f["name"].endswith("_id")
        ]
        if len(dates) != 1 or len(nums) != 1:
            continue
        found.append((_entity_table_name(ent), nums[0], dates[0], _snake(cls)))
    return found[0] if len(found) == 1 else None


def _limit_status_body(m, ent, params, returns, entities_by_class, limit_cls):
    """Body lines for a limit-status method, or None when the shape differs."""
    ret_l = (returns or "").strip().lower()
    # A status is a STRING: anything that names rows, a mapping or a number
    # belongs to another recipe (and never to this one).
    if "str" not in ret_l:
        return None
    if any(t in ret_l for t in ("list", "dict", "int", "float", "bool")):
        return None
    placement = _period_and_fk(ent, list(params or []))
    if placement is None:
        return None
    fk_param, fk_col, period_param, period_col = placement
    limit_fields = _limit_fields(ent)
    if limit_fields is None:
        return None
    limit_field, period_field, fk_field = limit_fields
    if fk_col != fk_field or period_col != period_field:
        return None
    spend = _spend_shape(entities_by_class, fk_field, limit_cls)
    if spend is None:
        return None
    table, amount_col, date_col, spend_var = spend
    return [
        "        period = str(%s)[:7]" % period_param,
        "        limit = None",
        "        for _row in self.list(%s=%s):" % (fk_param, fk_param),
        "            if str(_row.%s)[:7] == period:" % period_field,
        "                limit = int(_row.%s or 0)" % limit_field,
        "                break",
        "        with self.db.connect() as conn:",
        "            total_row = conn.execute(",
        "                \"SELECT COALESCE(SUM(%s), 0) AS n FROM %s \""
        % (amount_col, table),
        "                \"WHERE %s = ? AND substr(%s, 1, 7) = ?\"," % (
            fk_field, date_col,
        ),
        "                (%s, period)," % fk_param,
        "            ).fetchone()",
        "            spent = int(total_row['n'] or 0)",
        "        if limit is None:",
        "            return %r" % STATUS_OK,
        "        if spent > limit:",
        "            return %r" % STATUS_OVER,
        "        if limit > 0 and spent * %d >= limit * %d:"
        % (_WARN_RATIO_DEN, _WARN_RATIO_NUM),
        "            return %r" % STATUS_WARN,
        "        return %r" % STATUS_OK,
    ]
