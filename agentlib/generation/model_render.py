"""Deterministic renderers for generated project skeleton files.

Extracted from agent.py: exceptions file, domain models file, and the
repository column mapper. These produce verbatim the same bytes the
original monolithic generator emitted — no behaviour change.
"""
from ..naming import _bare, _camel, _plural, _pluralize_table_name

_BOOL_TRUE = ("true", "1", "yes", "y")
_BOOL_FALSE = ("false", "0", "no", "n")


def _coerce_field_default(ftype, dflt):
    """Coerce a designed field default to the field's declared Python type.

    STRICT: a default whose JSON shape does not match the field type is
    REJECTED (returns None), so the field stays required exactly as before
    this feature. The small model has been caught emitting a dict
    (``{"value": "cash", "type": "str"}``) as a ``str`` default, which
    rendered ``payment_method: str = {...}`` — an invalid mutable dataclass
    default that broke the ENTIRE models import. Only a scalar of the right
    shape is accepted; strings may spell booleans/ints ("true"/"1").
    """
    if dflt is None or isinstance(dflt, (dict, list, tuple, set)):
        return None
    try:
        if ftype in ("bool", "boolean"):
            if isinstance(dflt, bool):
                return dflt
            if isinstance(dflt, str):
                low = dflt.strip().lower()
                if low in _BOOL_TRUE:
                    return True
                if low in _BOOL_FALSE:
                    return False
            return None
        if ftype == "int" and not isinstance(dflt, bool):
            return int(dflt) if isinstance(dflt, (int, float, str)) else None
        if ftype == "float" and not isinstance(dflt, bool):
            return float(dflt) if isinstance(dflt, (int, float, str)) else None
        if ftype in ("str", "date", "datetime"):
            return dflt if isinstance(dflt, str) else None
    except (TypeError, ValueError):
        return None
    return None


def _render_exceptions_file(design):
    names = design.get("exceptions") or []
    lines = ['"""Custom exceptions."""', "from __future__ import annotations", ""]
    for n in names:
        lines.append("class %s(Exception):" % n)
        lines.append('    """Raised by %s."""' % n)
        lines.append("")
        lines.append("")
    if not names:
        lines.append("pass")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _annotation(ftype):
    """The annotation text for a declared date/datetime field type.

    The models module imports the ``datetime`` MODULE (its ``__post_init__``
    stamps ``datetime.datetime.now()``), so a datetime column written as the
    bare word ``datetime`` annotated THE MODULE, not the class — an incoherent
    annotation (S-inventory "annotation naming a module"). A ``date`` column
    stays bare, because the module also imports ``from datetime import date``.
    """
    if ftype == "datetime":
        return "datetime.datetime"
    return ftype


def _render_models_file(design):
    """dataclasses from the entities design.

    Table-level UNIQUE pairs (unique_together) are emitted as a
    UNIQUE_TOGETHER constant so the deterministic DDL generator can pick
    them up from the model AST — no spec-text sniffing anywhere.
    """
    blocks = []
    unique_map = {}
    table_map = {}
    needs_datetime = False
    needs_date = False
    for ent in design.get("entities") or []:
        name = ent["name"]
        # Declared table name kept ONLY when it differs from the
        # deterministic rule (irregular plurals like Person -> people).
        tn = (ent.get("table_name") or "").strip()
        if tn and tn != _pluralize_table_name(name):
            table_map[name] = tn
        fields = ent.get("fields") or []
        req, opt, defaulted, auto_now = [], [], [], []
        for f in fields:
            fname = f.get("name")
            ftype = f.get("type", "str")
            # A date/datetime annotation is emitted VERBATIM below, so the
            # matching name must be imported or the annotation is unbound.
            if ftype == "date":
                needs_date = True
            elif ftype == "datetime":
                needs_datetime = True
            dflt = _coerce_field_default(ftype, f.get("default"))
            if fname == "id":
                opt.append((fname, f.get("type", "int")))
            elif dflt is not None:
                # A spec-declared default (e.g. available_copies default 1,
                # is_active default True, low_active default False) becomes a
                # real dataclass default so constructing the entity without it
                # yields the spec value. This runs BEFORE the nullable branch:
                # a NULLABLE field whose spec also declares a default
                # (inventory's "low_active (optional bool, default False)")
                # would otherwise drop to None and lose the specified value.
                defaulted.append((fname, ftype, dflt, bool(f.get("nullable"))))
            elif f.get("nullable"):
                opt.append((fname, f.get("type", "int")))
            elif (
                f.get("auto") == "now"
                and f.get("type") in ("date", "datetime")
            ):
                # A non-nullable auto:"now" timestamp is stamped by the
                # dataclass itself, so omitting it is safe. This keeps the
                # dataclass CONSISTENT with _required_constructor_fields,
                # which already excludes such fields from the required list:
                # otherwise the fill hint hides a field the constructor
                # demands -> a guaranteed reject + retry (the borrow_member
                # loan_date class of defect).
                opt.append((fname, "datetime"))
                auto_now.append(fname)
                needs_datetime = True
            else:
                req.append((fname, f.get("type", "str")))
        parts = [
            "    %s: %s" % (fname, _annotation(ftype))
            for fname, ftype in req
        ]
        for fname, ftype, dflt, nullable in defaulted:
            ann = (
                "Optional[%s]" % _bare(_annotation(ftype))
                if nullable else _annotation(ftype)
            )
            parts.append("    %s: %s = %r" % (fname, ann, dflt))
        parts += [
            "    %s: Optional[%s] = None" % (fname, _bare(_annotation(ftype)))
            for fname, ftype in opt
        ]
        body = "\n".join(parts)
        if auto_now:
            body += "\n\n    def __post_init__(self):\n"
            for af in auto_now:
                body += "        if self.%s is None:\n" % af
                body += (
                    "            self.%s = "
                    "datetime.datetime.now().isoformat()\n" % af
                )
        blocks.append("@dataclass\nclass %s:\n%s" % (name, body))
        pairs = [
            [str(c) for c in pair]
            for pair in (ent.get("unique_together") or [])
            if isinstance(pair, (list, tuple)) and len(pair) >= 1
        ]
        # Synthesize single-column UNIQUE(<field>) from per-field unique flags
        # (e.g. sku unique=True) that aren't already covered by a declared
        # unique_together pair. The deterministic DDL generator only reads
        # __unique_together__, so single-field uniques must surface here or
        # they are silently dropped — the root cause of the inventory defect.
        covered = set()
        for p in pairs:
            covered.update(p)
        for f in fields:
            # 'id' is the PRIMARY KEY AUTOINCREMENT column; a separate
            # UNIQUE(id) is redundant, so skip it in synthesis (a declared
            # unique_together involving id is still honored above).
            if (f.get("unique") and f.get("name") and f["name"] != "id"
                    and f["name"] not in covered):
                pairs.append([f["name"]])
                covered.add(f["name"])
        if pairs:
            unique_map[name] = pairs
    if unique_map:
        const_lines = ["UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {"]
        for cls, pairs in sorted(unique_map.items()):
            # A single-element pair must render as a 1-tuple ("sku",) so the
            # AST extractor sees a real tuple (("sku") is just a string).
            parts = []
            for p in pairs:
                s = ", ".join('"%s"' % c for c in p)
                if len(p) == 1:
                    s += ","
                parts.append("(%s)" % s)
            const_lines.append('    "%s": [%s],' % (cls, ", ".join(parts)))
        const_lines.append("}")
        blocks.append("\n".join(const_lines))
    if table_map:
        const_lines = ["TABLE_NAMES: Dict[str, str] = {"]
        for cls, tbl in sorted(table_map.items()):
            const_lines.append('    "%s": "%s",' % (cls, tbl))
        const_lines.append("}")
        blocks.append("\n".join(const_lines))
    header = (
        '"""Domain models."""\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n"
        + ("from datetime import date\n" if needs_date else "")
        + ("import datetime\n" if needs_datetime else "")
        + "from typing import Dict, List, Optional\n"
    )
    return header + "\n\n\n".join(blocks) + "\n"


def _repo_columns(ent_design, table_names=None):
    """[(name, sql, is_id, fk_ref_snake)] for a repo entity.

    `table_names` maps designed class name -> declared table name so FK
    references resolve to declared (possibly irregular) table names."""
    fields = ent_design.get("fields") or []
    cols = []
    for f in fields:
        fname = f.get("name")
        ftype = f.get("type", "str")
        if fname == "id":
            cols.append(("id", "INTEGER PRIMARY KEY AUTOINCREMENT", True, None))
            continue
        sql = {
            "str": "TEXT", "int": "INTEGER", "float": "REAL",
            "bool": "INTEGER", "date": "TEXT", "datetime": "TEXT",
        }.get(ftype, "TEXT")
        if not f.get("nullable"):
            sql += " NOT NULL"
        if f.get("unique"):
            sql += " UNIQUE"
        ref = None
        if fname.endswith("_id") and fname != "id":
            base = fname[: -len("_id")]
            # Same rule as the DDL: the referenced table is named after the
            # CLASS the column points at, so the stem is camelised before the
            # plural is formed (`assigned_to_user_id` -> AssignedToUser ->
            # `assignedtousers`). Pluralising the raw column stem produced
            # `assigned_to_users`, a table no CREATE made (prompt 47).
            ref = (
                (table_names or {}).get(_camel(base))
                or _pluralize_table_name(_camel(base))
            )
        cols.append((fname, sql, False, ref))
    return cols
