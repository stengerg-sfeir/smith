"""Repository finder recipe: deterministic get/find/list_<e>_by_<col> bodies.

Registered as a discoverable `RECIPES` list under the kernel repo package.
"""
import re

from ...design import _feas_entity_fields
from ...naming import _camel, _entity_table_name, _pluralize_table_name
from ..recipe_types import Recipe

_FINDER_NAME_RE = re.compile(
    r"^(?:get|find|list|fetch)_(.+)_by_(.+)$"
)


def _feas_entity_date_cols(ent):
    return [
        f.get("name") for f in (ent.get("fields") or [])
        if isinstance(f, dict) and f.get("type") in ("date", "datetime")
    ]


def _simple_finder_spec(attr, meth, entities_by_class):
    """Broadened DETERMINISTIC lookup spec. Matches
    get/find/list/fetch_<entity(s)>_by_<column> (or _<col>_range) on that
    entity's OWN repo. Returns a dict with `kind` ('single'|'list'|'range')
    plus render/interface details, or None — never guesses."""
    match = _FINDER_NAME_RE.match(meth or "")
    if not match:
        return None
    ent_snake, col = match.group(1), match.group(2)
    is_plural = ent_snake.endswith("s") and len(ent_snake) > 3
    ent_sing = ent_snake[:-1] if is_plural else ent_snake
    if attr != ent_sing + "_repo":
        return None
    cls = _camel(ent_sing)
    ent = entities_by_class.get(cls) or {}
    table = (
        _entity_table_name(ent) if ent else _pluralize_table_name(ent_sing)
    )
    # ---- date-range finder: get_<entity>s_by_<date>_range ------------------
    if col.endswith("_range"):
        base = col[: -len("_range")]
        dcols = _feas_entity_date_cols(ent)
        dcol = None
        if base in dcols:
            dcol = base
        elif len(dcols) == 1:
            dcol = dcols[0]
        if dcol is None:
            return None
        return {
            "kind": "range",
            "meth": meth,
            "date_col": dcol,
            "cls": cls,
            "table": table,
            "params": [("start_date", True), ("end_date", True)],
            "ret": "List[%s]" % cls,
        }
    # ---- scalar single / plural list lookup --------------------------------
    ftypes = _feas_entity_fields(ent)
    py = ftypes.get(col) or ("int" if col == "id" else "")
    if col != "id" and py not in ("str", "int", "float", "bool"):
        return None
    kind = "list" if is_plural else "single"
    ret = "List[%s]" % cls if kind == "list" else "Optional[%s]" % cls
    return {
        "kind": kind,
        "meth": meth,
        "col": col,
        "cls": cls,
        "table": table,
        "py": "int" if col == "id" else py,
        "params": [(col, True)],
        "ret": ret,
    }


def _render_simple_finder(spec):
    """Deterministic repo method body for the broadened finder spec."""
    kind = spec.get("kind", "single")
    if kind == "range":
        return (
            "    def %(meth)s(self, start_date: str, end_date: str) -> List[%(cls)s]:\n"
            "        with self.db.connect() as conn:\n"
            "            rows = conn.execute(\n"
            '                "SELECT * FROM %(table)s WHERE %(date_col)s BETWEEN ? AND ?",'
            "                (start_date, end_date)\n"
            "            ).fetchall()\n"
            "            return [%(cls)s(**dict(r)) for r in rows]" % spec
        )
    if kind == "list":
        return (
            "    def %(meth)s(self, %(col)s: %(py)s) -> List[%(cls)s]:\n"
            "        with self.db.connect() as conn:\n"
            "            rows = conn.execute(\n"
            '                "SELECT * FROM %(table)s WHERE %(col)s = ?", (%(col)s,)\n'
            "            ).fetchall()\n"
            "            return [%(cls)s(**dict(r)) for r in rows]" % spec
        )
    return (
        "    def %(meth)s(self, %(col)s: %(py)s) -> Optional[%(cls)s]:\n"
        "        with self.db.connect() as conn:\n"
        "            row = conn.execute(\n"
        '                "SELECT * FROM %(table)s WHERE %(col)s = ?", (%(col)s,)\n'
        "            ).fetchone()\n"
        "            return %(cls)s(**dict(row)) if row else None" % spec
    )


def _try_finder_body(attr, meth, entities_by_class):
    """Recipe fn: return the finder body when it applies, else None."""
    spec = _simple_finder_spec(attr, meth, entities_by_class)
    if spec is None:
        return None
    return [_render_simple_finder(spec)]


RECIPES = [Recipe("simple_finder", 20, _try_finder_body)]
