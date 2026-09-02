"""Reconstruct the "produced design" from generated code (AST).

The code-gen manifest isn't persisted, but the generated project IS the
materialized design. This module AST-parses the generated ``.py`` files to
rebuild a design-shaped dict (entities, fields, types, nullability, FKs,
unique constraints, exceptions, repositories, services). Names come
deterministically from the actual code, so there is no LLM naming drift
(whence the earlier ``Tasknotfound`` problem disappears by construction).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from agentlib.naming import _camel, _snake

_TRIGGER_BY_NAME = (
    ("not_found", ("notfound", "not_found", "missing")),
    ("validation", ("validation", "invalid")),
    ("conflict", ("conflict", "alreadyexists", "duplicate", "exists")),
    ("constraint", ("constraint", "integrity")),
)

_PY_TYPES = {"str", "int", "float", "bool", "date", "datetime"}


def _singular(word: str) -> str:
    """Naive English plural -> singular: categories -> category, products -> product."""
    w = word.strip()
    low = w.lower()
    if low.endswith("ies") and len(low) > 3:
        return w[: -3] + "y"
    if low.endswith("sses"):
        return w[: -2]
    if low.endswith("s") and not low.endswith("ss"):
        return w[:-1]
    return w


def _normalize_type(ann_str: str) -> str | None:
    """Map a type annotation string to one of the spec primitives."""
    s = ann_str.strip()
    low = s.lower()
    for py_t in _PY_TYPES:
        if py_t in low:
            return py_t
    return None


def _field_nullable(ann_str: str, default: ast.expr | None) -> bool:
    s = ann_str.strip()
    if "optional" in s.lower() or "none" in s.lower():
        return True
    return default is not None


def _parse_fields(cls: ast.ClassDef) -> list[dict]:
    fields = []
    for node in cls.body:
        if not isinstance(node, ast.AnnAssign) or not isinstance(node.target, ast.Name):
            continue
        name = node.target.id
        type_str = ast.unparse(node.annotation) if node.annotation else ""
        ftype = _normalize_type(type_str) or "str"
        is_pk = name == "id"
        # SQLite PRIMARY KEY columns are NOT NULL. The dataclass writes
        # `id: Optional[int] = None` (a Python default), but that is NOT a
        # nullable SQL column. Do not conflate the two, or the auditor
        # reports an invalid "nullable primary key".
        fields.append({
            "name": name,
            "type": ftype,
            "nullable": False if is_pk else _field_nullable(type_str, node.value),
            "unique": False,  # refined from DDL below
            "primary_key": is_pk,
            "auto": "autoincrement" if is_pk else None,
            "default": ast.unparse(node.value) if node.value is not None else None,
        })
    return fields


def _parse_exceptions(path: Path) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        # Emit exceptions regardless of inherit target (generated exceptions
        # subclass Exception); the structural/behaviour value is the class.
        name = node.name
        low = name.lower()
        trigger = "custom"
        for trig, needles in _TRIGGER_BY_NAME:
            if any(n in low for n in needles):
                trigger = trig
                break
        out.append({"name": name, "trigger": trigger})
    return out


def _parse_repo_service(path: Path, suffix: str) -> list[dict]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    out = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or not node.name.endswith(suffix):
            continue
        entity = node.name[: -len(suffix)] or ""
        methods = []
        for m in node.body:
            if not isinstance(m, ast.FunctionDef):
                continue
            if m.name.startswith("__"):
                continue
            params = [
                {"name": a.arg, "type": (ast.unparse(a.annotation) if a.annotation else "")}
                for a in m.args.args
                if a.arg != "self"
            ]
            methods.append({
                "name": m.name,
                "params": params,
                "returns": ast.unparse(m.returns) if m.returns else "",
            })
        out.append({
            "module": str(Path(path).stem),
            "class": node.name,
            "entity": entity,
            "methods": methods,
        })
    return out


def _parse_cli_db_path(cli_path: Path) -> str | None:
    """Extract the SQLite file a click CLI connects to (``DB_PATH = '...'``).

    ``design_extract`` previously hardcoded ``database_file = "app.db"``, but
    generated CLIs pick their own file (``DB_PATH = "library.db"``,
    ``DB_PATH = "inventory.db"``). The facade seed synthesis
    (``_make_sql_seed_plan``) inserts seed rows into this file, so a mismatch
    silently seeds a different DB than the app reads, and the app then fails an
    FK check (library_system ``book-add`` → ``FOREIGN KEY constraint failed``).
    """
    if not cli_path.exists():
        return None
    try:
        text = cli_path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"\bDB_PATH\b\s*=\s*['\"]([^'\"]+)['\"]", text)
    if m:
        return m.group(1)
    m = re.search(r"\bdb_path\b\s*=\s*['\"]([^'\"]+)['\"]", text)
    return m.group(1) if m else None


def _parse_cli(cli_path: Path) -> dict:
    """Parse a click CLI into {commands: [{name, flags}]}.

    Handles ``@group.command()`` / ``@cli.command()`` decorated functions and
    their ``@click.option('-f', '--flag', ...)`` / ``@click.argument(...)``.
    Flags are normalized to their long-name dest (``--is-active`` -> ``is_active``).
    """
    if not cli_path.exists():
        return {"commands": []}
    try:
        tree = ast.parse(cli_path.read_text(encoding="utf-8"))
    except SyntaxError:
        return {"commands": []}

    commands = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        is_command = False
        for dec in node.decorator_list:
            # @<anything>.command() / @<anything>.group() / @click.command()
            fn = dec.func if isinstance(dec, ast.Call) else dec
            if isinstance(fn, ast.Attribute) and fn.attr in ("command", "group"):
                is_command = True
            elif isinstance(fn, ast.Name) and fn.id == "command":
                is_command = True
        if not is_command:
            continue
        flags = []
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            fn = dec.func
            if isinstance(fn, ast.Attribute) and fn.attr in ("option", "argument"):
                for arg in dec.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        v = arg.value
                        if v.startswith("--"):
                            flags.append(v.lstrip("-").replace("-", "_"))
                        elif v.startswith("-") and flags:
                            continue  # short alias, dest already from long
        commands.append({"name": node.name, "flags": flags})
    return {"commands": commands}


def _parse_fks_uniques(database: Path, entities: list[dict]) -> tuple[dict[str, list[dict]], dict[str, list[list[str]]], dict[str, str]]:
    """Parse FOREIGN KEY + UNIQUE constraints out of the DDL.

    Returns (fks_by_entity, unique_together_by_entity, table_by_entity) keyed
    by entity name, merged onto the entity dicts by the caller.
    """
    try:
        text = database.read_text(encoding="utf-8")
    except OSError:
        return {}, {}, {}

    # FOREIGN KEY (col) REFERENCES table (id)
    fk_pat = re.compile(
        r"FOREIGN KEY\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*"
        r"REFERENCES\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(",
        re.IGNORECASE,
    )
    # UNIQUE( a, b ) or a UNIQUE column
    unique_pat = re.compile(r"UNIQUE\s*\(([^)]*)\)", re.IGNORECASE)

    fks_by_entity: dict[str, list[dict]] = {}
    unique_by_entity: dict[str, list[list[str]]] = {}
    table_by_entity: dict[str, str] = {}

    # Split CREATE TABLE blocks to attribute constraints to the right entity.
    blocks = re.split(r"CREATE TABLE IF NOT EXISTS\s+([A-Za-z_][A-Za-z0-9_]*)",
                      text, flags=re.IGNORECASE)
    for i in range(1, len(blocks), 2):
        table = blocks[i].strip()
        body = blocks[i + 1] if i + 1 < len(blocks) else ""
        # map table -> entity by singularizing: categories -> Category
        sing = _singular(table)
        ent = next((e for e in entities if _snake(e["name"]) == sing), None)
        if ent is None:
            # Compound entity names: table 'invoicelines' singularizes to
            # 'invoiceline', matching _snake('InvoiceLine') = 'invoice_line'
            # once underscores are removed. Compare against the SINGULAR form,
            # not the raw (plural) table name.
            ent = next((e for e in entities
                        if _snake(e["name"]).replace("_", "") == sing.replace("_", "")),
                       None)
        if ent is None:
            continue
        ents = ent["name"]
        table_by_entity[ents] = table
        for m in fk_pat.finditer(body):
            fks_by_entity.setdefault(ents, []).append({
                "field": m.group(1).strip(),
                "ref": _camel(_singular(m.group(2).strip())),
            })
        for m in unique_pat.finditer(body):
            cols = [c.strip() for c in m.group(1).split(",") if c.strip()]
            if cols:
                unique_by_entity.setdefault(ents, []).append(cols)
    return fks_by_entity, unique_by_entity, table_by_entity


def extract_design(project_dir: Path) -> dict:
    """Reconstruct a design dict from a generated project directory."""
    # Need a named tuple for cross-reference; entities list is mutated.
    fks_by_entity: dict[str, list[dict]] = {}
    unique_by_entity: dict[str, list[list[str]]] = {}

    entities: list[dict] = []
    models_path = project_dir / "models.py"
    if models_path.exists():
        try:
            tree = ast.parse(models_path.read_text(encoding="utf-8"))
        except SyntaxError:
            tree = ast.Module(body=[], type_ignores=[])
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                is_dataclass = any(
                    isinstance(d, ast.Name) and d.id == "dataclass"
                    for d in node.decorator_list
                )
                entities.append({
                    "name": node.name,
                    "table_name": "",
                    "fields": _parse_fields(node),
                    "unique_together": [],
                    "fks": [],
                })

    database_path = project_dir / "database.py"
    table_by_entity: dict[str, str] = {}
    if database_path.exists():
        fks_by_entity, unique_by_entity, table_by_entity = _parse_fks_uniques(database_path, entities)
    for ent in entities:
        ent["fks"] = fks_by_entity.get(ent["name"], [])
        ent["unique_together"] = unique_by_entity.get(ent["name"], [])
        ent["table_name"] = table_by_entity.get(ent["name"], "")

    exceptions: list[dict] = []
    exc_path = project_dir / "exceptions.py"
    if exc_path.exists():
        exceptions = _parse_exceptions(exc_path)

    repositories: list[dict] = []
    services: list[dict] = []
    for p in sorted(project_dir.rglob("*.py")):
        if p.name in ("models.py", "exceptions.py", "database.py", "main.py", "__init__.py"):
            continue
        if p.name.endswith("_repository.py"):
            repositories.extend(_parse_repo_service(p, "Repository"))
        elif p.name.endswith("_service.py"):
            services.extend(_parse_repo_service(p, "Service"))

    # Infer list_filters / unique on fields from DDL where possible.
    for ent in entities:
        field_names = {f["name"] for f in ent["fields"]}
        for cols in ent.get("unique_together", []):
            for c in cols:
                if c in field_names:
                    for f in ent["fields"]:
                        if f["name"] == c:
                            f["unique"] = True

    db_path = project_dir / "database.py"
    foreign_keys_enabled = False
    if db_path.exists():
        try:
            foreign_keys_enabled = "PRAGMA foreign_keys = ON" in db_path.read_text(encoding="utf-8")
        except OSError:
            foreign_keys_enabled = False
    return {
        "database_file": _parse_cli_db_path(project_dir / "cli.py") or "app.db",
        "entities": entities,
        "exceptions": exceptions,
        "repositories": repositories,
        "services": services,
        "cli": _parse_cli(project_dir / "cli.py"),
        "foreign_keys_enabled": foreign_keys_enabled,
    }
