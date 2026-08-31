"""Service recipe: count rows grouped by declared fields -> [ {group: count} ].

Registered as a discoverable `RECIPES` list under the kernel service package.
Unlike ``sum_by_group`` (sums a numeric field), this counts 1 per row — the
grouped-count shape for ``List[Dict]``-returning list methods whose LLM fill
tends to sum a date column (``0 + row.start_date``). The count is always a
literal ``1`` per row, never a field value.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _filter_params


def _h_count_by_group(m, impl, ent, entities_by_class):
    """Count rows grouped by the declared fields -> [ {group field: value, ...,
    'count': n} ]. The group tuple is built from the declared ``group_by``
    fields; each row contributes ``+1`` (a count, never a date/numeric field)."""
    var = _snake(impl["entity"])
    gb = list(impl["group_by"])
    declared = set(_filter_params(ent))
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    kwargs = [p for p in params if p in declared]
    args = ", ".join("%s=%s" % (p, p) for p in kwargs)
    key_tuple = ", ".join("row.%s" % g for g in gb)
    entries = []
    for i, g in enumerate(gb):
        entries.append("                    '%s': key[%d]," % (g, i))
    return [
        "        results = []",
        "        groups = {}",
        "        for row in self.%s_repo.list(%s):" % (var, args),
        "            key = (%s)" % key_tuple,
        "            groups[key] = groups.get(key, 0) + 1",
        "        for key, count in groups.items():",
        "            results.append({",
    ] + entries + [
        "                    'count': count,",
        "                })",
        "        return results",
    ]


RECIPES = [Recipe("count_by_group", 12, _h_count_by_group)]
