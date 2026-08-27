"""Service recipe: sum a numeric field over rows filtered by the method's params.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _filter_params


def _h_total_filtered(m, impl, ent, entities_by_class):
    """Sum value_field over rows filtered by the method's declared params."""
    var = _snake(impl["entity"])
    vf = impl["value_field"]
    rk = impl.get("result_key") or "total"
    declared = set(_filter_params(ent))
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    kwargs = [p for p in params if p in declared]
    if not kwargs:
        return None
    call = ", ".join("%s=%s" % (p, p) for p in kwargs)
    head = ["        rows = self.%s_repo.list(%s)" % (var, call)]
    returns = m.get("returns") or ""
    if "Dict" not in returns and "dict" not in returns:
        return head + ["        return sum(e.%s for e in rows)" % vf]
    return head + [
        "        total = sum(e.%s for e in rows)" % vf,
        "        return {'%s': total}" % rk,
    ]


RECIPES = [Recipe("total_filtered", 11, _h_total_filtered)]
