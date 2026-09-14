"""Service recipe: render a report's spec-stated PARTS.

Registered as a discoverable `RECIPES` list under the kernel service package.

Input `impl` (built by ``agentlib.pipeline.method_contract.compile_contract_impl``
from a contract extracted from the SPECIFICATION, never from the code):

    {"kind": "report_parts", "entity": "expense",
     "value_field": "amount_cents", "date_field": "expense_date",
     "period_param": "month", "period_granularity": "month",
     "group_field": "category_id",
     "parts": ["total", "per_category", "budget_status"],
     "budget": {"entity": "budget", "limit_field": "amount_limit_cents",
                "fk_filter_param": "category_id", "month_filter_param": "month"},
     "labels": {"ok": "on_track", "warn": "warning", "over": "exceeded"},
     "result_key": "total"}

Why this exists. Expenses' ``get_monthly_report(month)`` and
``get_yearly_summary(year)`` are *compound* reports: the specification names
the pieces they must return ("total spent, per-category breakdown, budget
status (on_track/warning/exceeded)" / "monthly totals, top spending
categories, average monthly spend"). A 4B fill produced plausible dicts that
silently dropped pieces — and no *crash* filter can see a missing key, so the
gap shipped (S1/S2).

The PARTS come from the specification (the "requirement analyst" contract),
but every *shape* used to render them comes from the DESIGN: which entity is
summed, on which declared list() filters the period is bounded, which column
groups it, and (for ``budget_status``) which entity holds the limit and how
its filter parameters are declared. Nothing here is keyed on a method name or
a domain word.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _declared_filters

# The fraction of a limit at which the specification's middle state
# ("warning") starts. The specification names the three states but not the
# boundary, so ONE documented default is chosen here rather than invented per
# method: at or above 80% of the limit is a warning, above it an exceedance,
# below it on track. A contract may override the LABELS (they are the spec's
# words) but not the ratio (the spec never states one).
_WARN_RATIO = 0.8

_DEFAULT_LABELS = {"ok": "on_track", "warn": "warning", "over": "exceeded"}


def _bounds(ent, df, pp, gran):
    """(start_filter_param, end_filter_param, lo_expr, hi_expr) or Nones.

    The period is bounded through the entity's OWN declared gte/lte filters
    over its date column — the same pair ``total_in_period`` uses — so the
    emitted ``list(...)`` call is the repository's real API.
    """
    p_start = p_end = None
    for p, col, op in _declared_filters(ent):
        if col != df:
            continue
        if op == "gte" and p_start is None:
            p_start = p
        elif op == "lte" and p_end is None:
            p_end = p
    if not p_start or not p_end:
        return None, None, None, None
    if gran == "year":
        return p_start, p_end, "str(%s) + '-01-01'" % pp, "str(%s) + '-12-31'" % pp
    return p_start, p_end, "%s + '-01'" % pp, "%s + '-31'" % pp


def _budget_block(impl, entities_by_class, pp):
    """Body lines for the per-category budget status, or None when unusable.

    The status needs a limit PER (group value, period): a designed entity
    carrying the group's foreign key, the limit, and a period column, plus the
    repository's own declared filter parameters for those two columns, so the
    lookup stays a plain ``list(...)`` call on the real API.
    """
    spec = impl.get("budget") or {}
    cls = next(
        (
            c for c in (entities_by_class or {})
            if _snake(c) == _snake(spec.get("entity") or "")
        ),
        None,
    )
    if cls is None:
        return None
    ent = entities_by_class[cls]
    fields = {
        f.get("name") for f in (ent.get("fields") or [])
        if isinstance(f, dict)
    }
    limit = spec.get("limit_field")
    if limit not in fields:
        return None
    fk_param = spec.get("fk_filter_param")
    month_param = spec.get("month_filter_param")
    declared = {p for p, _, _ in _declared_filters(ent)}
    if fk_param not in declared or month_param not in declared:
        return None
    labels = dict(_DEFAULT_LABELS)
    for k, v in (impl.get("labels") or {}).items():
        if k in labels and isinstance(v, str) and v:
            labels[k] = v
    var = _snake(cls)
    return [
        "        budget_status = {}",
        "        for key, spent in per_category.items():",
        "            limit = None",
        "            for _row in self.%s_repo.list(%s=key, %s=%s):"
        % (var, fk_param, month_param, pp),
        "                limit = _row.%s" % limit,
        "            if limit is None:",
        "                budget_status[key] = %r" % labels["ok"],
        "            elif spent > limit:",
        "                budget_status[key] = %r" % labels["over"],
        "            elif spent >= limit * %s:" % _WARN_RATIO,
        "                budget_status[key] = %r" % labels["warn"],
        "            else:",
        "                budget_status[key] = %r" % labels["ok"],
    ]


def _h_report_parts(m, impl, ent, entities_by_class):
    """Render the contract's parts over the entity's declared period filters."""
    var = _snake(impl["entity"])
    vf = impl["value_field"]
    df = impl["date_field"]
    pp = impl["period_param"]
    gran = impl.get("period_granularity") or "month"
    parts = list(impl.get("parts") or [])
    gf = impl.get("group_field")
    if not parts:
        return None
    if ("per_category" in parts or "budget_status" in parts
            or "top_categories" in parts) and not gf:
        return None
    if "budget_status" in parts and "per_category" not in parts:
        return None
    p_start, p_end, lo, hi = _bounds(ent, df, pp, gran)
    if p_start is None:
        return None

    lines = [
        "        rows = self.%s_repo.list(" % var,
        "            %s=%s," % (p_start, lo),
        "            %s=%s," % (p_end, hi),
        "        )",
        "        total = sum(e.%s for e in rows)" % vf,
    ]
    if "per_category" in parts:
        lines += [
            "        per_category = {}",
            "        for e in rows:",
            "            key = e.%s" % gf,
            "            per_category[key] = "
            "per_category.get(key, 0) + e.%s" % vf,
        ]
    if "count" in parts:
        lines.append("        count = len(rows)")
    if "monthly_totals" in parts:
        lines += [
            "        monthly_totals = {}",
            "        for e in rows:",
            "            stamp = e.%s" % df,
            "            if not stamp:",
            "                continue",
            "            month_key = str(stamp)[:7]",
            "            monthly_totals[month_key] = "
            "monthly_totals.get(month_key, 0) + e.%s" % vf,
        ]
    if "top_categories" in parts or "average_monthly" in parts:
        lines += [
            "        category_totals = {}",
            "        for e in rows:",
            "            cat_key = e.%s" % gf,
            "            category_totals[cat_key] = "
            "category_totals.get(cat_key, 0) + e.%s" % vf,
        ]
    if "budget_status" in parts:
        block = _budget_block(impl, entities_by_class, pp)
        if block is None:
            return None
        lines += block

    out = ["        result = {'%s': %s}" % (pp, pp)]
    if "total" in parts:
        out.append(
            "        result[%r] = total" % (impl.get("result_key") or "total")
        )
    if "count" in parts:
        out.append("        result['count'] = count")
    if "per_category" in parts:
        out.append("        result['per_category'] = per_category")
    if "monthly_totals" in parts:
        out.append("        result['monthly_totals'] = monthly_totals")
    if "top_categories" in parts:
        top_n = int(impl.get("top_n") or 3)
        out += [
            "        ranked = sorted(category_totals.items(),",
            "                        key=lambda kv: kv[1], reverse=True)",
            "        result['top_categories'] = [",
            "            {'category_id': key, 'total': value}"
            " for key, value in ranked[:%d]" % top_n,
            "        ]",
        ]
    if "average_monthly" in parts:
        out += [
            "        result['average_monthly_spend'] = (",
            "            total / len(monthly_totals) if monthly_totals else 0",
            "        )",
        ]
    if "budget_status" in parts:
        out.append("        result['budget_status'] = budget_status")
    out.append("        return result")
    return lines + out


RECIPES = [Recipe("report_parts", 15, _h_report_parts)]
