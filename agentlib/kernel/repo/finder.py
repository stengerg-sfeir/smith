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


def _resolve_col_token(tok, ftypes):
    """Resolve one ``_by_<tok>`` (or ``_and_`` part) to ``(column, pytype)``.

    Exact field-name match first, then the FK-stem form ``<tok>_id`` — so a
    ``_by_member_and_book`` finder resolves ``member`` -> ``member_id`` and
    ``book`` -> ``book_id`` on an entity whose FK columns are named that way,
    while a real column spelled ``member`` still wins. Only scalar columns
    (str/int/float/bool) or ``id`` qualify; anything else returns None so the
    caller declines rather than guessing a column.
    """
    cand = tok if tok in ftypes else (tok + "_id" if tok + "_id" in ftypes else None)
    if cand is None:
        return None
    py = ftypes.get(cand) or ("int" if cand == "id" else "")
    if cand != "id" and py not in ("str", "int", "float", "bool"):
        return None
    return (cand, "int" if cand == "id" else py)


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
    # Only synthesize a range finder when the `_range` suffix denotes an
    # actual date column (or an unambiguous date alias on an entity that has
    # exactly one date column). Otherwise we'd silently render
    # `WHERE <date_col> BETWEEN ? AND ?` for non-date ranges (e.g.
    # get_order_items_by_quantity_range would filter created_at) — wrong.
    if col.endswith("_range"):
        base = col[: -len("_range")]
        dcols = _feas_entity_date_cols(ent)
        dcol = None
        if base in dcols:
            dcol = base
        elif base in (
            "date", "created", "created_at", "updated", "updated_at",
            "timestamp", "datetime", "when", "created_on", "updated_on",
        ):
            if dcols:
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

    # ---- multi-column equality finder: <verb>_<e>_by_<a>_and_<b> ----------
    # `get_loan_by_member_and_book` names TWO columns joined by `_and_`. Every
    # token must resolve to a scalar (or FK-id) column of the entity's OWN
    # table, so the body is a plain two-predicate equality SELECT —
    # deterministic, no cross-table guess (the entity is fixed by the
    # `_<entity>_by_` stem and the repo it is asked on). Without this route
    # the name falls through to the variant-alias repair, which aliases it
    # onto a param-name-coverage-compatible method
    # (loan_repo.get_loan_by_member_and_book -> update_loan, a 6-param WRITE)
    # and the caller then fails on arity (library_system's borrow_book).
    if "_and_" in col:
        cols = []
        for tok in col.split("_and_"):
            resolved = _resolve_col_token(tok, ftypes)
            if resolved is None:
                return None
            cols.append(resolved)
        if len(cols) < 2:
            return None
        multi_kind = "list" if is_plural else "single"
        return {
            "kind": multi_kind,
            "meth": meth,
            "cols": cols,
            "cls": cls,
            "table": table,
            "py": None,
            "params": [(c, True) for c, _ in cols],
            "ret": (
                "List[%s]" % cls if multi_kind == "list" else "Optional[%s]" % cls
            ),
        }

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
    cols = spec.get("cols")
    if cols:
        where = " AND ".join("%s = ?" % c for c, _ in cols)
        sig = ", ".join("%s: %s" % (c, py) for c, py in cols)
        vals = "(" + ", ".join(c for c, _ in cols) + ")"
        cls = spec["cls"]
        lines = [
            "    def %s(self, %s) -> %s:" % (spec["meth"], sig, spec["ret"]),
            "        with self.db.connect() as conn:",
            '            sql = "SELECT * FROM %s WHERE %s"' % (spec["table"], where),
        ]
        if kind == "list":
            lines += [
                "            rows = conn.execute(sql, %s).fetchall()" % vals,
                "            return [%s(**dict(r)) for r in rows]" % cls,
            ]
        else:
            lines += [
                "            row = conn.execute(sql, %s).fetchone()" % vals,
                "            return %s(**dict(row)) if row else None" % cls,
            ]
        return "\n".join(lines)
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
