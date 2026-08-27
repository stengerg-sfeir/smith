"""Service recipe: group rows by declared fields, keep groups of >= min_count.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _filter_params


def _h_duplicate_groups(m, impl, ent, entities_by_class):
    """Group rows by the declared fields; keep groups of >= min_count."""
    var = _snake(impl["entity"])
    gb = list(impl["group_by"])
    mc = impl.get("min_count") or 2
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
        "            groups.setdefault(key, []).append(row)",
        "        for key, group in groups.items():",
        "            if len(group) >= %d:" % mc,
        "                results.append({",
    ] + entries + [
        "                    'count': len(group),",
        "                })",
        "        return results",
    ]


RECIPES = [Recipe("duplicate_groups", 13, _h_duplicate_groups)]
