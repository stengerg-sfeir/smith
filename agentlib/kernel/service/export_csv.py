"""Service recipe: write filtered rows to the declared file param as CSV.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _csv_chunk, _filter_params


def _h_export_csv(m, impl, ent, entities_by_class):
    """Write filtered rows to the declared file param as CSV."""
    var = _snake(impl["entity"])
    fp = impl["file_param"]
    headers = [
        f.get("name")
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    ]
    declared = set(_filter_params(ent))
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    kwargs = [p for p in params if p in declared and p != fp]
    args = ", ".join("%s=%s" % (p, p) for p in kwargs)
    suffix = ", " if args else ""
    lines = [
        "        rows = self.%s_repo.list(%s%s)" % (var, args, suffix),
        '        with open(%s, "w", newline="", encoding="utf-8") as f:' % fp,
        "            writer = csv.writer(f)",
        "            writer.writerow([",
    ]
    lines += [
        "                " + ", ".join("'%s'" % h for h in chunk) + ","
        for chunk in _csv_chunk(headers, 4)
    ]
    lines += [
        "            ])",
        "            for row in rows:",
        "                writer.writerow([",
    ]
    lines += [
        "                    " + ", ".join("row.%s" % h for h in chunk) + ","
        for chunk in _csv_chunk(headers, 4)
    ]
    lines += [
        "                ])",
    ]
    return lines


RECIPES = [Recipe("export_csv", 12, _h_export_csv)]
