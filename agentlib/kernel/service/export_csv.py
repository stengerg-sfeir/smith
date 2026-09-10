"""Service recipe: write filtered rows to the declared file param as CSV.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _snake
from ..recipe_types import Recipe
from .common import _csv_chunk, _resolve_filter_args


def _h_export_csv(m, impl, ent, entities_by_class):
    """Write filtered rows to the declared file param as CSV."""
    var = _snake(impl["entity"])
    fp = impl["file_param"]
    headers = [
        f.get("name")
        for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("name")
    ]
    # Resolve each designed param to a declared list() filter — by name, or
    # by date-range ROLE (the design's from_date/to_date IS the entity's
    # start_date/end_date gte/lte pair). Without this the export wrote the
    # UNFILTERED table whenever the design paraphrased the range names.
    resolved, _unresolved = _resolve_filter_args(m, ent)
    kwargs = [(f, mp) for f, mp in resolved if mp != fp]
    args = ", ".join("%s=%s" % (f, mp) for f, mp in kwargs)
    lines = [
        "        rows = self.%s_repo.list(%s)" % (var, args),
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
