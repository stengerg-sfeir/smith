"""Service recipe: sum value_field grouped by declared fields -> {group: total}.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _filter_params


def _h_sum_by_group(m, impl, ent, entities_by_class):
    """Sum value_field grouped by the declared fields -> {group: total}."""
    var = _snake(impl["entity"])
    vf = impl["value_field"]
    gb = list(impl["group_by"])
    declared = set(_filter_params(ent))
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    kwargs = [p for p in params if p in declared]
    args = ", ".join("%s=%s" % (p, p) for p in kwargs)
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
