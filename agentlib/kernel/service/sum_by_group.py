"""Service recipe: sum value_field grouped by declared fields -> {group: total}.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _resolve_filter_args


def _h_sum_by_group(m, impl, ent, entities_by_class):
    """Sum value_field grouped by the declared fields -> {group: total}."""
    var = _snake(impl["entity"])
    vf = impl["value_field"]
    gb = list(impl["group_by"])
    # Resolve each designed param to a declared list() filter — by name, or
    # by date-range ROLE (from_date/to_date -> the start_date/end_date
    # gte/lte pair). Exact-name-only matching silently dropped a paraphrased
    # range, grouping over the whole table instead of the requested window.
    resolved, _unresolved = _resolve_filter_args(m, ent)
    args = ", ".join("%s=%s" % (fp, mp) for fp, mp in resolved)
    call = "self.%s_repo.list(%s)" % (var, args)
    lines = ["        results = {}"]
    if len(gb) == 1:
        lines += [
            "        for row in %s:" % call,
            "            key = row.%s" % gb[0],
        ]
    else:
        key_tuple = ", ".join("row.%s" % g for g in gb)
        lines += [
            "        for row in %s:" % call,
            "            key = (%s)" % key_tuple,
        ]
    lines += [
        "            results[key] = results.get(key, 0) + row.%s" % vf,
        "        return results",
    ]
    return lines


RECIPES = [Recipe("sum_by_group", 14, _h_sum_by_group)]
