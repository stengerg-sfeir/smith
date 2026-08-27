"""Service recipe: sum a numeric field over one month/year bucket.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _declared_filters


def _h_total_in_period(m, impl, ent, entities_by_class):
    """Sum value_field over one month/year bucket of date_field."""
    var = _snake(impl["entity"])
    vf, df = impl["value_field"], impl["date_field"]
    pp, gran = impl["period_param"], impl["granularity"]
    rk = impl.get("result_key") or "total"
    p_start = p_end = None
    for p, c, op in _declared_filters(ent):
        if c == df and op == "gte" and p_start is None:
            p_start = p
        elif c == df and op == "lte" and p_end is None:
            p_end = p
    if not p_start or not p_end:
        return None
    if gran == "month":
        lo = "%s + '-01'" % pp
        hi = "%s + '-31'" % pp
    else:
        lo = "str(%s) + '-01-01'" % pp
        hi = "str(%s) + '-12-31'" % pp
    rows_lines = [
        "        rows = self.%s_repo.list(" % var,
        "            %s=%s," % (p_start, lo),
        "            %s=%s," % (p_end, hi),
        "        )",
    ]
    returns = m.get("returns") or ""
    if "Dict" not in returns and "dict" not in returns:
        return rows_lines + ["        return sum(e.%s for e in rows)" % vf]
    return rows_lines + [
        "        total = sum(e.%s for e in rows)" % vf,
        "        return {'%s': %s, '%s': total}" % (pp, pp, rk),
    ]


RECIPES = [Recipe("total_in_period", 10, _h_total_in_period)]
