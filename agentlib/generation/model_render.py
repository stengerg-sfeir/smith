"""Deterministic renderers for generated project skeleton files.

Extracted from agent.py: exceptions file, domain models file, and the
repository column mapper. These produce verbatim the same bytes the
original monolithic generator emitted — no behaviour change.
"""
from ..naming import _bare, _camel, _plural, _pluralize_table_name


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


def _render_models_file(design):
    """dataclasses from the entities design.

    Table-level UNIQUE pairs (unique_together) are emitted as a
    UNIQUE_TOGETHER constant so the deterministic DDL generator can pick
    them up from the model AST — no spec-text sniffing anywhere.
    """
    blocks = []
    unique_map = {}
    table_map = {}
    for ent in design.get("entities") or []:
        name = ent["name"]
        # Declared table name kept ONLY when it differs from the
        # deterministic rule (irregular plurals like Person -> people).
        tn = (ent.get("table_name") or "").strip()
        if tn and tn != _pluralize_table_name(name):
            table_map[name] = tn
        fields = ent.get("fields") or []
        req, opt = [], []
        for f in fields:
            if f.get("name") == "id" or f.get("nullable"):
                opt.append((f["name"], f.get("type", "int")))
            else:
                req.append((f["name"], f.get("type", "str")))
        parts = ["    %s: %s" % (fname, ftype) for fname, ftype in req]
        parts += ["    %s: Optional[%s] = None" % (fname, _bare(ftype))
                  for fname, ftype in opt]
        body = "\n".join(parts)
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
        "from typing import Dict, List, Optional\n"
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
            ref = (table_names or {}).get(_camel(base)) or _plural(base)
        cols.append((fname, sql, False, ref))
    return cols
