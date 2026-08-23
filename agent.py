#!/usr/bin/env python3
"""
Neurosymbolic Python Coding Agent

Generates Python code from natural-language prompts via a local
OpenAI-compatible LLM server. Structured design decisions are extracted as
schema-constrained JSON; mechanical files are rendered deterministically.

Validation pipeline (zero LLM cost):
  1. Syntax check (AST)
  2. Import resolution (AST)
  3. Structural checks (AST): required fields, classes, methods
  4. Mechanical fixes: relative imports, ruff --fix
  5. LLM repair: targeted, only failing files

Usage:
    python3 agent.py                    # Process all prompts
    python3 agent.py --prompt hello     # Process a specific prompt by name
    python3 agent.py --list             # List available prompts
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROMPTS_DIR = Path(__file__).parent / "prompts"
OUTPUT_DIR = Path(__file__).parent / "generated"

SYSTEM_CONTEXT = dedent("""\
    Expert Python engineer. Complete, runnable code.
    Rules: type hints, PEP 8, sqlite3 for DB, click for CLI.
    IDs = Optional[int], money = cents (int).
    No import *, no markdown, no commentary. Return raw code.
""")

# Local llama-server (symserver) OpenAI-compatible endpoint.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
# Cap for LONG free-text decodes (whole-file generation / skeleton fills).
# A fill that hits the cap is truncated -> fails validation -> burns a
# retry with a different context: a major hidden run-to-run variance
# source. Keep it well above the largest expected file.
LLM_MAX_TOKENS_LONG = int(os.environ.get("LLM_MAX_TOKENS_LONG", "8192"))


def _chat_completion(messages, max_tokens=2048, temperature=0.0, schema=None,
                     timeout=180):
    """Call the local OpenAI-compatible llama-server.

    When `schema` is a dict, it is passed as response_format so the server
    constrains generation with a GBNF grammar (smith's approach) — the model
    physically cannot emit malformed or out-of-schema JSON.
    """
    body = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if schema is not None:
        body["response_format"] = {"type": "json_object", "schema": schema}
    req = urllib.request.Request(
        LLM_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        # Truncated output: make it VISIBLE instead of letting it surface
        # later as a mysterious validation failure.
        print(
            "    [warn] completion hit max_tokens=%d — output truncated"
            % max_tokens,
            file=sys.stderr,
        )
    return choice["message"]["content"]


def _json_block(text):
    """Extract the first balanced JSON object from model output."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _json_complete(messages, schema=None, max_tokens=2048, attempts=2, verbose=False):
    """Constrained JSON completion: schema-enforced, else re-ask once.

    Returns a parsed JSON object, or None if both attempts fail to parse.
    """
    for attempt in range(attempts):
        raw = _chat_completion(messages, max_tokens=max_tokens, schema=schema)
        block = _json_block(raw)
        if block is None:
            if verbose:
                print("      JSON parse failed (attempt %d): %r" % (attempt + 1, raw[:120]))
            continue
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            if verbose:
                print("      JSON decode failed (attempt %d)" % (attempt + 1))
            continue
    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_prompt_name(raw):
    name = Path(raw).stem
    name = re.sub(r"^prompt_", "", name)
    return name

def discover_prompts():
    prompts = {}
    if PROMPTS_DIR.is_dir():
        for p in sorted(PROMPTS_DIR.glob("*.txt")):
            prompts[_normalise_prompt_name(p)] = p
    return prompts

def read_prompt(path):
    return path.read_text(encoding="utf-8").strip()

def _extract_code_block(text):
    m = re.match(r"^```(?:python)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text

def _split_multifile(code):
    marker = re.compile(r"(?:^|\n)\s*#\s*===\s*file:\s*(.+?)\s*===\s*\n", re.IGNORECASE)
    parts = marker.split(code)
    if len(parts) <= 1:
        return {"main.py": code}
    files = {}
    for i in range(1, len(parts), 2):
        filepath = parts[i].strip()
        file_content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        files[filepath] = file_content
    return files

def _output_name_for_prompt(prompt_name):
    return prompt_name.replace(" ", "_").lower()

def _join_files(files):
    """Re-join a dict of files into one code block (inverse of _split_multifile)."""
    if len(files) <= 1:
        return next(iter(files.values()), "")
    parts = []
    for name, content in files.items():
        parts.append("# === file: %s ===\n%s" % (name, content))
    return "\n\n".join(parts)


def _extract_defined_names(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names

def _extract_class_fields(source):
    """Extract field names from classes in source code.

    Handles:
      class Foo: field_name = ...
      class Foo: def __init__(self, field_name: type, ...)
    Returns dict of class_name -> set of field/method names.
    """
    result = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return result

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            fields = set()
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Assign):
                    for target in child.targets:
                        if isinstance(target, ast.Name) and not target.id.startswith("_"):
                            fields.add(target.id)
                elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name == "__init__":
                        for arg in child.args.args:
                            if arg.arg != "self":
                                fields.add(arg.arg)
                    elif not child.name.startswith("_"):
                        fields.add(child.name)
            result[node.name] = fields
    return result


# ---------------------------------------------------------------------------
# AST-based validation (zero LLM cost)
# ---------------------------------------------------------------------------

_STDLIB = {
    "abc", "argparse", "ast", "asyncio", "base64", "bisect", "calendar",
    "collections", "colorsys", "contextlib", "copy", "csv", "ctypes",
    "dataclasses", "datetime", "decimal", "difflib", "enum", "errno",
    "fcntl", "fnmatch", "fractions", "functools", "gc", "getpass",
    "glob", "gzip", "hashlib", "heapq", "hmac", "html", "http",
    "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "linecache", "locale", "logging", "lzma", "math",
    "mimetypes", "multiprocessing", "numbers", "operator", "os",
    "pathlib", "platform", "pickle", "pkgutil", "posixpath",
    "pprint", "queue", "random", "re", "readline", "secrets", "select",
    "shlex", "shutil", "signal", "site", "smtplib", "socket",
    "sqlite3", "ssl", "stat", "statistics", "string", "struct",
    "subprocess", "sys", "sysconfig", "tempfile", "textwrap", "threading",
    "time", "timeit", "token", "tokenize", "tomllib", "traceback",
    "types", "typing", "unicodedata", "unittest", "urllib", "uuid",
    "venv", "warnings", "weakref", "xml", "zipfile", "zipimport",
    "__future__",
}


def _check_syntax_and_imports(files, sibling_exports=None):
    """Check syntax and import resolution. Returns (errors, mechanical_fixes).

    `future` is valid in `from __future__ import annotations`; treat it as a
    builtin (it is not an importable module).
    """
    errors = []
    fixes = {}

    for fp, content in files.items():
        # 1. Syntax check
        try:
            ast.parse(content)
        except SyntaxError as e:
            errors.append("%s: SYNTAX ERROR: %s" % (fp, e))
            cleaned = re.sub(r"^```\w*\n", "", content.strip())
            cleaned = re.sub(r"\n```$", "", cleaned)
            if cleaned != content:
                try:
                    ast.parse(cleaned)
                    fixes[fp] = cleaned
                    errors[-1] = "%s: syntax fixed (removed fences)" % fp
                except SyntaxError:
                    pass
            continue

        # 2. Relative import fix
        new_content = content
        if re.search(r"from \.\w+", content):
            new_content = re.sub(r"from \.(\w+)", r"from \1", new_content)

        # 3. Sibling import validation
        if sibling_exports:
            file_stems = {Path(f).stem for f in files}
            all_exports = dict(sibling_exports)
            all_exports[Path(fp).stem] = _extract_defined_names(new_content)

            tree2 = ast.parse(new_content)
            for node in ast.walk(tree2):
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    mod = node.module
                    if mod in all_exports:
                        for alias in node.names:
                            if alias.name not in all_exports[mod]:
                                errors.append(
                                    "%s: '%s' not found in '%s' (has: %s)"
                                    % (fp, alias.name, mod, sorted(all_exports[mod]))
                                )
                    elif mod not in file_stems and mod not in _STDLIB:
                        errors.append("%s: nonexistent module '%s'" % (fp, mod))

        if new_content != content:
            fixes[fp] = new_content

    return errors, fixes


def _check_structural(files, design_ctx):
    """Design-driven structural validation (zero LLM cost, zero prompt sniffing).

    Validates the FINAL file tree against the schema-constrained designs
    (never against regex-scanned spec vocabulary):

    1. Every designed exception class is defined somewhere.
    2. Every designed entity model class is defined, with all its fields.
    3. Every designed service method is defined in the service file.

    Returns list of error strings with file hints.
    """
    errors = []
    all_code = "\n".join(files.values())

    # 1. Designed exception classes
    exc_fps = [fp for fp in files if "exception" in fp.lower()]
    exc_hint = exc_fps[0] if exc_fps else next(iter(files), "exceptions.py")
    for exc in design_ctx.get("exceptions") or []:
        if "class %s" % exc not in all_code:
            errors.append("%s: missing required exception '%s'" % (exc_hint, exc))

    # 2. Designed entity classes + fields
    model_fps = [fp for fp in files if "model" in fp.lower()]
    model_hint = model_fps[0] if model_fps else next(iter(files), "models.py")
    model_content = "\n".join(files[fp] for fp in model_fps)
    for cls, fields in (design_ctx.get("entities") or {}).items():
        if "class %s" % cls not in all_code:
            errors.append("%s: missing required class '%s'" % (model_hint, cls))
            continue
        for field in fields:
            if field not in model_content:
                errors.append("%s: missing required field '%s'" % (model_hint, field))

    # 3. Designed service methods
    svc_fp = design_ctx.get("service_file")
    if svc_fp and svc_fp in files:
        svc_content = files[svc_fp]
        for m in design_ctx.get("service_methods") or []:
            if "def %s" % m not in svc_content:
                errors.append("%s: missing required method '%s'" % (svc_fp, m))

    return errors


# ---------------------------------------------------------------------------
# DDL generation from models (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _extract_model_ast(files):
    """Extract model class definitions from model files.

    Returns dict of class_name -> list of (field_name, python_type_hint).
    Handles annotation-assignment (`field: type = default`), plain
    assignment, and __init__-based field definitions. Also captures the
    UNIQUE_TOGETHER constant into result["__unique_together__"] and the
    TABLE_NAMES constant into result["__table_names__"] when present.
    """
    result = {}
    model_files = [fp for fp in files if "model" in fp.lower()]

    for fp in model_files:
        try:
            tree = ast.parse(files[fp])
        except SyntaxError:
            continue

        for node in ast.iter_child_nodes(tree):
            # UNIQUE_TOGETHER constant emitted by _render_models_file
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "UNIQUE_TOGETHER"
                and isinstance(node.value, ast.Dict)
            ):
                umap = {}
                try:
                    for k, v in zip(node.value.keys, node.value.values):
                        cls = ast.literal_eval(k)
                        pairs = []
                        for elt in v.elts:
                            pairs.append([ast.literal_eval(e) for e in elt.elts])
                        umap[cls] = pairs
                except Exception:
                    umap = {}
                if umap:
                    merged = dict(result.get("__unique_together__") or {})
                    merged.update(umap)
                    result["__unique_together__"] = merged
                continue
            # TABLE_NAMES constant emitted by _render_models_file
            # (declared table names for entities with irregular plurals)
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "TABLE_NAMES"
                and isinstance(node.value, ast.Dict)
            ):
                tmap = {}
                try:
                    for k, v in zip(node.value.keys, node.value.values):
                        cls = ast.literal_eval(k)
                        tbl = ast.literal_eval(v)
                        if (
                            isinstance(cls, str) and cls
                            and isinstance(tbl, str) and tbl
                        ):
                            tmap[cls] = tbl
                except Exception:
                    tmap = {}
                if tmap:
                    merged = dict(result.get("__table_names__") or {})
                    merged.update(tmap)
                    result["__table_names__"] = merged
                continue
            if isinstance(node, ast.ClassDef):
                fields = []  # list of (name, type_hint_str)
                for child in ast.iter_child_nodes(node):
                    # dataclass style: name: str = None  -> ast.AnnAssign
                    if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                        if not child.target.id.startswith("_"):
                            type_hint = "ANY"
                            if child.annotation:
                                try:
                                    type_hint = ast.unparse(child.annotation)
                                except Exception:
                                    type_hint = "ANY"
                            fields.append((child.target.id, type_hint))
                    # plain assignment: name = None -> ast.Assign
                    elif isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                                fields.append((target.id, "ANY"))
                    # __init__(self, name: str) -> ast.FunctionDef
                    elif isinstance(child, ast.FunctionDef) and child.name == "__init__":
                        for arg in child.args.args:
                            if arg.arg != "self":
                                type_hint = "ANY"
                                if arg.annotation:
                                    try:
                                        type_hint = ast.unparse(arg.annotation)
                                    except Exception:
                                        type_hint = "ANY"
                                fields.append((arg.arg, type_hint))
                result[node.name] = fields

    return result


def _pluralize_table_name(class_name):
    """Singular class name -> plural lowercase table name.

    box -> boxes, city -> cities, task -> tasks.
    """
    lower = class_name.lower()
    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        return lower[:-1] + "ies"
    if lower.endswith("s"):
        return lower + "es"
    return lower + "s"


def _entity_table_name(ent):
    """Declared table name when the design declares one (irregular plural),
    else the deterministic rule over the class name."""
    ent = ent or {}
    tn = (ent.get("table_name") or "").strip()
    return tn or _pluralize_table_name(ent.get("name") or "")


def _python_type_to_sql(type_hint):
    """Map Python type hints to SQLite column types."""
    t = type_hint.lower()
    if "int" in t:
        return "INTEGER"
    if "bool" in t:
        return "BOOLEAN"
    if "str" in t or "text" in t or "string" in t:
        return "TEXT"
    if "float" in t or "decimal" in t:
        return "REAL"
    return "TEXT"


def _generate_ddl_from_models(model_classes):
    """Generate CREATE TABLE DDL from model class definitions.

    Model class names become table names (lowercase pluralized).
    Fields become columns. 'id' fields get PRIMARY KEY AUTOINCREMENT.
    Table-level UNIQUE pairs come from the models' UNIQUE_TOGETHER constant.
    """
    unique_map = model_classes.pop("__unique_together__", {})
    table_map = model_classes.pop("__table_names__", {})
    tables = []

    for class_name, fields in model_classes.items():
        table_name = table_map.get(class_name) or _pluralize_table_name(class_name)

        columns = []
        foreign_keys = []
        unique_constraints = []
        for pair in unique_map.get(class_name) or []:
            cols_sql = ", ".join(str(c) for c in pair)
            unique_constraints.append("    UNIQUE(%s)" % cols_sql)

        for field_name, type_hint in fields:
            sql_type = _python_type_to_sql(type_hint)
            col_def = "    %s %s" % (field_name, sql_type)

            if field_name == "id":
                col_def += " PRIMARY KEY AUTOINCREMENT"
            elif "Optional" in type_hint:
                # Allow NULL for Optional fields
                pass
            else:
                col_def += " NOT NULL"

            columns.append(col_def)

            # Detect foreign key patterns
            if field_name.endswith("_id") and field_name != "id":
                base = field_name[: -len("_id")]
                ref_table = table_map.get(_camel(base)) or _pluralize_table_name(base)
                foreign_keys.append(
                    "    FOREIGN KEY (%s) REFERENCES %s (id)" % (field_name, ref_table)
                )

        # Build CREATE TABLE (terminate with ';' so executescript
        # splits statements correctly)
        all_parts = columns + foreign_keys + unique_constraints
        ddl = "CREATE TABLE IF NOT EXISTS %s (\n%s\n);" % (
            table_name,
            ",\n".join(all_parts)
        )
        tables.append(ddl)

    return "\n\n".join(tables)


def _generate_database_file(model_classes, db_filename="app.db"):
    """Generate a complete database.py from model AST definitions.

    Uses a list-based template to guarantee clean line indentation --
    no dedent/tab pitfalls. DDL is emitted via cursor.executescript()
    with a triple-quoted string, so column/table lines never become
    bare statements inside the function body. `db_filename` is the spec's
    own SQLite filename (declared in the layout design) used as the
    init_database() default — nothing is hardcoded here.
    """
    ddl = _generate_ddl_from_models(model_classes)

    # Indent each DDL line by 8 spaces (continuation of the string arg)
    indented_ddl = "\n".join("        " + line if line.strip() else line
                             for line in ddl.split("\n"))

    lines = [
        "import sqlite3",
        "from contextlib import contextmanager",
        "from pathlib import Path",
        "",
        "",
        "class Database:",
        '    """SQLite database wrapper with automatic table creation."""',
        "",
        '    def __init__(self, db_path: str = ":memory:"):',
        '        """Initialize connection path and create tables."""',
        "        self.db_path = db_path",
        '        if db_path != ":memory:":',
        "            parent = Path(db_path).parent",
        "            if parent and not parent.exists():",
        "                parent.mkdir(parents=True, exist_ok=True)",
        "        self._init_tables()",
        "",
        '    def connect(self) -> sqlite3.Connection:',
        '        """Open a new connection with foreign keys enabled."""',
        "        conn = sqlite3.connect(self.db_path)",
        "        conn.row_factory = sqlite3.Row",
        '        conn.execute("PRAGMA foreign_keys = ON")',
        "        return conn",
        "",
        '    def _init_tables(self) -> None:',
        '        """Create all required tables if they do not exist."""',
        "        with self.connect() as conn:",
        "            create_tables(conn)",
        "",
        "",
        'def get_db_connection(db_path: str = ":memory:") -> sqlite3.Connection:',
        '    """Create a new database connection with foreign keys enabled."""',
        "    conn = sqlite3.connect(db_path)",
        "    conn.row_factory = sqlite3.Row",
        '    conn.execute("PRAGMA foreign_keys = ON")',
        "    return conn",
        "",
        "",
        '@contextmanager',
        'def get_connection(db_path: str = ":memory:"):',
        '    """Context manager for database connection."""',
        "    conn = get_db_connection(db_path)",
        "    try:",
        "        yield conn",
        "        conn.commit()",
        "    except Exception:",
        "        conn.rollback()",
        "        raise",
        "    finally:",
        "        conn.close()",
        "",
        "",
        "def create_tables(conn: sqlite3.Connection) -> None:",
        '    """Create all required tables."""',
        "    cursor = conn.cursor()",
        '    cursor.execute("PRAGMA foreign_keys = ON")',
        "    cursor.executescript(",
        '        """' + indented_ddl + '"""',
        "    )",
        "    conn.commit()",
        "",
        "",
        'def init_database(db_path: str = "%s") -> sqlite3.Connection:' % db_filename,
        '    """Initialize database with tables and return connection."""',
        "    conn = get_db_connection(db_path)",
        "    create_tables(conn)",
        "    return conn",
    ]
    return "\n".join(lines)


def _run_ruff_fix(project_dir):
    """Run ruff --fix on the generated project directory."""
    try:
        subprocess.run(
            ["ruff", "check", "--fix", "--select", "E,F,I,W", str(project_dir)],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # ruff not available or timed out


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------

def generate_code(prompt_text):
    """Free-text generation against the local OpenAI-compatible server."""
    messages = [
        {"role": "system", "content": SYSTEM_CONTEXT},
        {"role": "user", "content": prompt_text},
    ]
    return _chat_completion(messages, max_tokens=LLM_MAX_TOKENS_LONG).strip()


def generate_with_validation(prompt_text, spec_text="", sibling_exports=None,
                             verbose=False, max_retries=3):
    """Generate code with AST validation and retry."""
    last_result = None
    for attempt in range(max_retries):
        raw = generate_code(prompt_text)
        code = _extract_code_block(raw)
        last_result = code

        files = _split_multifile(code)
        errors, fixes = _check_syntax_and_imports(files, sibling_exports)

        for fp, fixed_content in fixes.items():
            files[fp] = fixed_content
            code = _join_files(files)

        real_errors = [e for e in errors if "SYNTAX" in e or "not found" in e or "nonexistent" in e]

        if not real_errors:
            if verbose and attempt > 0:
                print("      V Fixed on attempt %d" % (attempt + 1))
            return code

        if verbose:
            print("      X Attempt %d: %s" % (attempt + 1, real_errors[0]))

        if attempt < max_retries - 1:
            prompt_text = (
                prompt_text
                + "\n\nFIX THESE ERRORS:\n"
                + "\n".join("  - %s" % e for e in real_errors)
                + "\n\nReturn ONLY the corrected raw Python source code."
            )

    return last_result


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

_MANIFEST_KINDS = (
    "exceptions", "models", "repository", "service", "cli", "main", "other",
)


def _manifest_schema():
    """Layout design schema. Files carry DECLARED metadata (kind, entity) so
    downstream phases never sniff the prompt text; `database_file` carries
    the spec's own SQLite filename so no component hardcodes one."""
    return {
        "type": "object",
        "properties": {
            "database_file": {"type": "string"},
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "role": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": list(_MANIFEST_KINDS),
                        },
                        "entity": {"type": "string"},
                        "imports_from": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["file", "role", "kind"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["files"],
        "additionalProperties": False,
    }


_MANIFEST_SYSTEM = (
    "You are an expert Python architect. Plan the FILE LAYOUT of a Python "
    "project from its specification. Output JSON with a \"files\" array "
    "(flat filenames like \"models.py\", no __init__.py, max 6-8 files) and "
    "a \"database_file\" string: the SQLite database filename the spec "
    "names (e.g. \"finance.db\"), or \"app.db\" when it names none. Each "
    "file entry: {\"file\", \"role\", \"kind\", \"entity\", "
    "\"imports_from\"} where kind is one of %s. \"entity\" is the "
    "snake_case domain entity the module owns — REQUIRED for repository and "
    "service kinds, omit it otherwise. \"imports_from\" lists sibling file "
    "stems this file imports from."
) % ", ".join(_MANIFEST_KINDS)


def _infer_manifest_kind(stem):
    """Deterministic fallback when the layout design omits `kind`."""
    if "exception" in stem:
        return "exceptions"
    if "model" in stem:
        return "models"
    if stem.endswith("_repository") or stem in ("repository", "repositories"):
        return "repository"
    if stem.endswith("_service") or stem in ("service", "services"):
        return "service"
    if stem == "cli":
        return "cli"
    if stem in ("main", "app"):
        return "main"
    return "other"


def _generate_manifest(prompt_text, verbose=False):
    """Schema-constrained layout design (grammar-enforced JSON, no fences)."""
    user = "SPECIFICATION:\n%s\n\nEmit the file-layout JSON now." % prompt_text
    messages = [
        {"role": "system", "content": _MANIFEST_SYSTEM},
        {"role": "user", "content": user},
    ]
    for attempt in (0, 1):
        data = _json_complete(messages, schema=_manifest_schema(), verbose=verbose)
        if isinstance(data, dict) and data.get("files"):
            return data
    return None


def _validate_manifest(data):
    """Normalize the layout design: flat filenames, declared kinds/entities,
    resolvable imports. Returns (files, db_file)."""
    db_file = str(data.get("database_file") or "").strip()
    if not re.match(r"^[\w.-]+\.db$", db_file):
        db_file = "app.db"
    cleaned = []
    for spec in data["files"]:
        original = spec.get("file") or ""
        flat = Path(original).name
        if flat == "__init__.py" or not flat.endswith(".py"):
            continue
        spec["file"] = flat
        # Declared kind wins, but an absent/"other"/invalid declaration falls
        # back to the deterministic filename inference so a mislabeled
        # models.py can never silently drop out of the design phase.
        if spec.get("kind") not in _MANIFEST_KINDS or spec["kind"] == "other":
            spec["kind"] = _infer_manifest_kind(Path(flat).stem)
        ent = spec.get("entity")
        spec["entity"] = ent.strip() if isinstance(ent, str) else ""
        spec["imports_from"] = [
            Path(d).name if "/" in d else d
            for d in spec.get("imports_from", [])
        ]
        cleaned.append(spec)
    file_stems = {Path(s["file"]).stem for s in cleaned}
    for spec in cleaned:
        spec["imports_from"] = [
            i for i in spec.get("imports_from", []) if i in file_stems
        ]
    # database.py is always generated deterministically from the model AST
    cleaned = [s for s in cleaned if Path(s["file"]).stem != "database"]
    return cleaned, db_file


# ---------------------------------------------------------------------------
# Semantic routing (schema-constrained) — replaces the fixed keyword list
# that decided multi- vs single-pass generation.
# ---------------------------------------------------------------------------

def _route_schema():
    return {
        "type": "object",
        "properties": {"mode": {"type": "string", "enum": ["single", "multi"]}},
        "required": ["mode"],
        "additionalProperties": False,
    }


_ROUTE_SYSTEM = (
    "You classify software specifications. Decide whether the specification "
    "describes a MULTI-MODULE project (several cooperating modules such as "
    "models, repositories, services, a CLI — a structured application) or a "
    "SINGLE-file script/tool. Output {\"mode\": \"multi\"} or "
    "{\"mode\": \"single\"}."
)


def _route_mode(prompt_text, verbose=False):
    messages = [
        {"role": "system", "content": _ROUTE_SYSTEM},
        {
            "role": "user",
            "content": "SPECIFICATION:\n%s\n\nClassify now." % prompt_text,
        },
    ]
    for attempt in (0, 1):
        data = _json_complete(messages, schema=_route_schema(), verbose=verbose)
        if isinstance(data, dict) and data.get("mode") in ("single", "multi"):
            return data["mode"]
    return "single"


# ---------------------------------------------------------------------------
# Manifest-first design (smith-style: schema-constrained JSON, no file bodies)
#
# The LLM only emits STRUCTURE as JSON under a GBNF grammar, so it cannot
# invent method signatures, classes, or fields. Everything mechanical is
# rendered deterministically from this manifest; the LLM fills only business
# bodies (service + repository custom methods) inside locked skeletons.
# ---------------------------------------------------------------------------

_NAME_SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
_NAME_CLASS = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


def _entities_schema():
    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "table_name": {"type": "string"},
                        "fields": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {
                                        "type": "string",
                                        "enum": [
                                            "str", "int", "float", "bool",
                                            "date", "datetime",
                                        ],
                                    },
                                    "unique": {"type": "boolean"},
                                    "nullable": {"type": "boolean"},
                                    "auto": {"type": "string", "enum": ["now"]},
                                },
                                "required": ["name", "type"],
                                "additionalProperties": False,
                            },
                        },
                        "unique_together": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "list_filters": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "param": {"type": "string"},
                                    "column": {"type": "string"},
                                    "op": {
                                        "type": "string",
                                        "enum": ["eq", "gte", "lte"],
                                    },
                                },
                                "required": ["param", "column", "op"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["name", "fields"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["entities"],
        "additionalProperties": False,
    }


_IMPL_KINDS = (
    "total_in_period", "total_filtered", "export_csv", "duplicate_groups",
    "list_filtered", "sum_by_group", "below_foreign_threshold",
)


def _methods_schema():
    """Method design schema with an optional declarative `impl` object.

    `impl` tells the deterministic renderer HOW to build the method body
    (which entity/fields/params it operates on) so agent.py needs no
    name- or suffix-based domain heuristics. Kinds:
      - total_in_period: sum value_field over a month/year bucket of
        date_field; period taken from period_param.
      - total_filtered:  sum value_field over rows filtered by the method's
        own params that match the entity's declared list_filters.
      - export_csv:      write filtered rows to file_param as CSV.
      - duplicate_groups: group rows by group_by fields, keep count >= min_count.
      - list_filtered:   repository listing delegating to self.list(**params)
        restricted to the entity's declared list_filters (no name sniffing).
    """
    return {
        "type": "object",
        "properties": {
            "methods": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "params": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "type": {"type": "string"},
                                },
                                "required": ["name", "type"],
                                "additionalProperties": False,
                            },
                        },
                        "returns": {"type": "string"},
                        "impl": {
                            "type": "object",
                            "properties": {
                                "kind": {"type": "string", "enum": list(_IMPL_KINDS)},
                                "entity": {"type": "string"},
                                "value_field": {"type": "string"},
                                "date_field": {"type": "string"},
                                "period_param": {"type": "string"},
                                "granularity": {
                                    "type": "string",
                                    "enum": ["month", "year"],
                                },
                                "result_key": {"type": "string"},
                                "file_param": {"type": "string"},
                                "group_by": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                                "min_count": {"type": "integer"},
                            },
                            "required": ["kind"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["name", "params", "returns"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["methods"],
        "additionalProperties": False,
    }


def _exceptions_schema():
    return {
        "type": "object",
        "properties": {
            "exceptions": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["exceptions"],
        "additionalProperties": False,
    }


# --- deterministic validators (schema may be bypassed by some backends) ----

def _v_exceptions(d):
    ex = d.get("exceptions") if isinstance(d, dict) else None
    if not isinstance(ex, list):
        return ["exceptions must be an array"]
    errs = []
    for e in ex:
        if not isinstance(e, str) or not _NAME_CLASS.match(e):
            errs.append("bad exception class %r" % (e,))
    return errs


def _v_entities(d):
    ents = d.get("entities") if isinstance(d, dict) else None
    if not isinstance(ents, list) or not ents:
        return ["entities must be a non-empty array"]
    errs = []
    for ent in ents:
        if not isinstance(ent, dict):
            errs.append("entity not an object")
            continue
        name = ent.get("name")
        if not isinstance(name, str) or not _NAME_CLASS.match(name):
            errs.append("bad entity name %r" % (name,))
        # Declared table name for irregular plurals (Person -> people);
        # empty/invalid declarations fall back to the deterministic rule.
        tn = ent.get("table_name")
        ent["table_name"] = tn.strip() if isinstance(tn, str) else ""
        fields = ent.get("fields")
        if not isinstance(fields, list) or not fields:
            errs.append("%s: no fields" % (name,))
            continue
        for f in fields:
            if not isinstance(f, dict):
                errs.append("%s: field not an object" % (name,))
                continue
            fname, ftype = f.get("name"), f.get("type")
            if not isinstance(fname, str) or not _NAME_SNAKE.match(fname):
                errs.append("%s: bad field name %r" % (name, fname))
            if ftype not in ("str", "int", "float", "bool", "date", "datetime"):
                errs.append("%s: bad type %r for field %r" % (name, ftype, fname))
            # Declared insert-time auto-fill ("now" = creation timestamp);
            # anything else normalizes to no auto-fill.
            if f.get("auto") != "now":
                f.pop("auto", None)
        # Declared list() filters: param/column snake_case, column must be a
        # real field of THIS entity, params unique. This declaration replaces
        # every suffix-based filter heuristic in the renderers.
        lf = ent.get("list_filters")
        if lf is not None:
            if not isinstance(lf, list):
                errs.append("%s: list_filters must be an array" % (name,))
            else:
                seen_params = set()
                for spec in lf:
                    if not isinstance(spec, dict):
                        errs.append("%s: list_filter not an object" % (name,))
                        continue
                    p, c = spec.get("param"), spec.get("column")
                    op = spec.get("op")
                    if not isinstance(p, str) or not _NAME_SNAKE.match(p):
                        errs.append("%s: bad list_filter param %r" % (name, p))
                    if not isinstance(c, str) or not _NAME_SNAKE.match(c):
                        errs.append("%s: bad list_filter column %r" % (name, c))
                    elif c not in {f.get("name") for f in fields}:
                        errs.append(
                            "%s: list_filter column %r is not a field" % (name, c)
                        )
                    if op not in ("eq", "gte", "lte"):
                        errs.append("%s: bad list_filter op %r" % (name, op))
                    if isinstance(p, str) and p in seen_params:
                        errs.append("%s: duplicate list_filter param %r" % (name, p))
                    seen_params.add(p if isinstance(p, str) else "")
    return errs


# Per-kind required bindings for a declarative service `impl`. Entity/field/
# param references are cross-checked against the designs at render time
# (_sanitize_impls); here we only enforce shape.
_IMPL_REQUIRED = {
    "total_in_period": (
        "entity", "value_field", "date_field", "period_param",
        "granularity", "result_key",
    ),
    "total_filtered": ("entity", "value_field", "result_key"),
    "export_csv": ("entity", "file_param"),
    "duplicate_groups": ("entity", "group_by"),
    "list_filtered": (),
    "sum_by_group": ("entity", "value_field", "group_by"),
    "below_foreign_threshold": (
        "entity", "value_field", "ref_entity", "ref_field", "fk_field",
    ),
}


def _v_impl(m, label):
    impl = m.get("impl")
    if impl is None:
        return []
    if not isinstance(impl, dict):
        return ["%s.%s: impl must be an object" % (label, m.get("name"))]
    errs = []
    kind = impl.get("kind")
    if kind not in _IMPL_KINDS:
        errs.append("%s.%s: unknown impl kind %r" % (label, m.get("name"), kind))
        return errs
    for key in _IMPL_REQUIRED[kind]:
        v = impl.get(key)
        if v is None or v == "" or v == []:
            errs.append("%s.%s: impl.%s missing for kind %s"
                        % (label, m.get("name"), key, kind))
    ent = impl.get("entity")
    if (
        isinstance(ent, str) and ent
        and not (_NAME_SNAKE.match(ent) or _NAME_CLASS.match(ent))
    ):
        errs.append("%s.%s: impl.entity must be an identifier"
                    % (label, m.get("name")))
    ref = impl.get("ref_entity")
    if (
        isinstance(ref, str) and ref
        and not (_NAME_SNAKE.match(ref) or _NAME_CLASS.match(ref))
    ):
        errs.append("%s.%s: impl.ref_entity must be an identifier"
                    % (label, m.get("name")))
    for key in ("value_field", "date_field", "period_param", "file_param",
                "ref_field", "fk_field"):
        v = impl.get(key)
        if isinstance(v, str) and v and not _NAME_SNAKE.match(v):
            errs.append("%s.%s: impl.%s must be snake_case"
                        % (label, m.get("name"), key))
    rk = impl.get("result_key")
    if isinstance(rk, str) and rk and not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", rk):
        errs.append("%s.%s: impl.result_key must be an identifier"
                    % (label, m.get("name")))
    gb = impl.get("group_by")
    if isinstance(gb, list):
        for g in gb:
            if not isinstance(g, str) or not _NAME_SNAKE.match(g):
                errs.append("%s.%s: impl.group_by entries must be snake_case"
                            % (label, m.get("name")))
    mc = impl.get("min_count")
    if mc is not None and (not isinstance(mc, int) or isinstance(mc, bool) or mc < 2):
        errs.append("%s.%s: impl.min_count must be an integer >= 2"
                    % (label, m.get("name")))
    return errs


def _normalize_impl(m):
    """Rescue common formatting mistakes in a designed impl object.

    The 4B model frequently emits near-miss bindings: "monthly" instead of
    "month", type annotations glued to names ("month: str"), PascalCase or
    pluralized references, string numbers. Normalizing these beats
    rejecting them — an impl that survives normalization renders
    deterministically instead of degrading to a stub.
    """
    impl = m.get("impl")
    if not isinstance(impl, dict):
        return

    def clean_ident(v, lower=False):
        v = str(v).split(":")[0].split("(")[0].strip().strip("$").strip()
        return v.lower() if lower else _snake(v)

    g = impl.get("granularity")
    if g == "monthly":
        impl["granularity"] = "month"
    elif g == "yearly":
        impl["granularity"] = "year"

    for key in ("entity", "value_field", "date_field", "period_param",
                "result_key", "file_param", "ref_entity", "ref_field",
                "fk_field"):
        if isinstance(impl.get(key), str) and impl[key]:
            impl[key] = clean_ident(
                impl[key], lower=key in ("entity", "ref_entity")
            )

    gb = impl.get("group_by")
    if isinstance(gb, list):
        impl["group_by"] = [
            clean_ident(g) for g in gb
            if isinstance(g, (str, int)) and str(g).strip()
        ]

    mc = impl.get("min_count")
    if isinstance(mc, str) and mc.strip().isdigit():
        impl["min_count"] = int(mc.strip())


def _strip_invalid_impls(d):
    """Remove impl objects that still fail shape validation after
    normalization (services/repositories designs).

    An invalid impl is a malformed optimization hint, not a structural
    error: the affected method simply degrades to CRUD delegation or a
    locked stub. Stripping keeps a bad hint from burning design retries
    or failing the whole pipeline. Returns the number of impls removed.
    """
    removed = 0
    for m in d.get("methods") or []:
        if not isinstance(m, dict) or m.get("impl") is None:
            continue
        _normalize_impl(m)
        if _v_impl(m, ""):
            del m["impl"]
            removed += 1
    return removed


def _strip_invalid_list_filters(d):
    """Drop invalid list_filter declarations in-place (models design).

    A list_filter that references a column the entity does not have, uses
    a malformed param/op, or duplicates another param is an optimization
    hint, not a structural error: list() simply renders fewer filters.
    Stripping keeps a bad hint from burning design retries or failing the
    whole pipeline (mirrors _strip_invalid_impls). Returns the number of
    filter entries removed.
    """
    dropped = 0
    ents = d.get("entities") if isinstance(d, dict) else None
    if not isinstance(ents, list):
        return 0
    for ent in ents:
        if not isinstance(ent, dict):
            continue
        lf = ent.get("list_filters")
        if lf is None:
            continue
        if not isinstance(lf, list):
            ent["list_filters"] = []
            dropped += 1
            continue
        fields = {
            f.get("name")
            for f in ent.get("fields") or []
            if isinstance(f, dict)
        }
        kept, seen = [], set()
        for spec in lf:
            ok = False
            if isinstance(spec, dict):
                p, c, op = spec.get("param"), spec.get("column"), spec.get("op")
                ok = (
                    isinstance(p, str) and bool(_NAME_SNAKE.match(p))
                    and isinstance(c, str) and bool(_NAME_SNAKE.match(c))
                    and c in fields
                    and op in ("eq", "gte", "lte")
                    and p not in seen
                )
                if ok:
                    seen.add(p)
            if ok:
                kept.append(spec)
            else:
                dropped += 1
        ent["list_filters"] = kept
    return dropped


def _v_methods(d, label):
    ms = d.get("methods") if isinstance(d, dict) else None
    if not isinstance(ms, list):
        return ["methods must be an array"]
    errs = []
    for m in ms:
        if not isinstance(m, dict):
            errs.append("%s: method not an object" % label)
            continue
        nm = m.get("name")
        if not isinstance(nm, str) or not _NAME_SNAKE.match(nm):
            errs.append("%s: bad method name %r" % (label, nm))
        params = m.get("params")
        if not isinstance(params, list):
            errs.append("%s.%s: params must be an array" % (label, nm))
            continue
        for p in params:
            if not isinstance(p, dict):
                errs.append("%s.%s: param not an object" % (label, nm))
                continue
            if not isinstance(p.get("name"), str) or not _NAME_SNAKE.match(p.get("name")):
                errs.append("%s.%s: bad param %r" % (label, nm, p.get("name")))
        errs.extend(_v_impl(m, label))
    return errs


_DESIGN_SYSTEMS = {
    "exceptions": (
        "You are an expert Python architect. Design the exceptions module of a "
        "Python project from its specification. Output JSON with an "
        '"exceptions" array of custom exception class names (PascalCase) the '
        "spec requires (e.g. NotFoundError, ValidationException). Only list "
        "exceptions the spec explicitly mentions."
    ),
    "models": (
        "You are an expert Python architect. Design a model (data) module from "
        'the specification. Output JSON with an "entities" array. Each entity: '
        '{"name": "PascalCase", "fields": [{"name", "type", "unique", '
        '"nullable"}]}. Types are primitives: str, int, float, bool, date, '
        'datetime. Set "unique": true for columns the spec says must be unique. '
        'Set "nullable": true for optional columns (default None), including '
        'the primary key id. When the spec names table-level uniqueness '
        '(e.g. "UNIQUE(a, b)"), fill the "unique_together" pairs of that '
        'entity. Also declare the "list_filters" of each entity: the query '
        'parameters its repository list() should accept, as {"param", '
        '"column", "op"} entries where op is "eq" (equality) or "gte"/"lte" '
        '(lower/upper bound of a range over a date-like column). Declare only '
        'filters the listing/filtering features in the spec imply; omit '
        '"list_filters" when none apply. Per field, set "auto": "now" when '
        'the spec implies the system stamps that field at creation time '
        '(e.g. a created_at timestamp); omit "auto" otherwise. Set '
        '"table_name" on an entity ONLY when its natural plural is '
        'irregular (e.g. Person -> people, Child -> children); omit it for '
        'regular plurals. Do not invent fields the spec does not imply.'
    ),
    "repositories": (
        "You are an expert Python architect. Design the CUSTOM methods of a "
        "data-access (repository) module. Basic CRUD (create/get_by_id/"
        "list/update/delete) is generated automatically, so do NOT list it. "
        'Output JSON with a "methods" array of the project-specific methods '
        "the spec needs (filters, totals, reports). Each method: "
        '{"name", "params": [{"name", "type"}], "returns"}. Use "" for no '
        "params or returns. When a method is a pure filtered listing whose "
        "params all map to this entity's declared list_filters, add "
        '{"impl": {"kind": "list_filtered"}} so its body is generated '
        "deterministically."
    ),
    "services": (
        "You are an expert Python architect. Design a service module that "
        "holds the BUSINESS LOGIC of the project. Output JSON with a "
        '"methods" array. Each method: {"name", "params": [{"name", "type"}], '
        '"returns"}. Use "Optional[T]"/"List[T]"/"Dict" for shapes. Use the '
        "exact field names and exceptions from the spec. One method per use "
        'case the spec describes. Use "" for no params or returns. '
        "When a use case matches one of these mechanical shapes, add an "
        '"impl" object to that method: every method that totals a numeric '
        "field, exports rows to a CSV file, or finds repeated rows MUST "
        "carry impl so its body is generated deterministically: "
        '{"kind": "total_in_period", "entity": "<entity snake_case>", '
        '"value_field": "<numeric field>", "date_field": "<date-like field>", '
        '"period_param": "<param holding a YYYY-MM month or a YYYY year>", '
        '"granularity": "month"|"year", "result_key": "<dict key for the '
        'total>"} (total over one period bucket; pick a short snake_case '
        "result_key naming the total, like total_spent); "
        '{"kind": "total_filtered", "entity": ..., "value_field": ..., '
        '"result_key": ...} (total over rows filtered by the params of this '
        "method that match the declared list_filters of the entity); "
        '{"kind": "export_csv", "entity": ..., "file_param": "<param receiving '
        'the output file path>"} (write filtered rows as CSV); '
        '{"kind": "duplicate_groups", "entity": ..., "group_by": ["<field>", '
        '...], "min_count": 2} (rows sharing the same group_by values, '
        "repeated occurrences); "
        '{"kind": "sum_by_group", "entity": ..., "value_field": ..., '
        '"group_by": ["<field>", ...]} (sum of value_field grouped by the '
        "group_by fields, one dict entry per group); "
        '{"kind": "below_foreign_threshold", "entity": ..., '
        '"value_field": "<numeric field of entity>", "ref_entity": '
        '"<related entity snake_case>", "ref_field": "<threshold field on '
        'the related entity>", "fk_field": "<foreign-key column on entity '
        'pointing at ref_entity>"} (rows whose value_field is strictly '
        "below the related row's ref_field, joined through fk_field). "
        "impl bindings must reference EXACTLY the entity/field/param names "
        "already designed; entity is the snake_case name of a designed "
        "entity. Methods that match none of these shapes get no impl."
    ),
}


def _cli_schema():
    return {
        "type": "object",
        "properties": {
            "commands": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "group": {"type": "array", "items": {"type": "string"}},
                        "name": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "required": {"type": "boolean"},
                                    "type": {
                                        "type": "string",
                                        "enum": ["str", "int", "flag"],
                                    },
                                    "field": {"type": "string"},
                                },
                                "required": ["name", "required", "type"],
                                "additionalProperties": False,
                            },
                        },
                        "target": {"type": "string"},
                    },
                    "required": ["group", "name", "options", "target"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["commands"],
        "additionalProperties": False,
    }


def _v_cli(d):
    cmds = d.get("commands") if isinstance(d, dict) else None
    if not isinstance(cmds, list) or not cmds:
        return ["commands must be a non-empty array"]
    errs = []
    for c in cmds:
        if not isinstance(c, dict):
            errs.append("command not an object")
            continue
        group = c.get("group")
        name = c.get("name")
        if not isinstance(group, list) or not group or not all(
            isinstance(g, str) and _NAME_SNAKE.fullmatch(g) for g in group
        ):
            errs.append("%s: bad group" % (name,))
        if not isinstance(name, str) or not _NAME_SNAKE.fullmatch(name):
            errs.append("bad command name %r" % (name,))
            continue
        # NOTE: duplicate paths are NOT rejected here — the model often
        # expresses a nested group ("product report") both as parent intent
        # and as leaf, and the deterministic renderer already resolves flat
        # collisions with numeric suffixes. Rejecting duplicates here burned
        # the whole CLI design for nothing.
        opts = c.get("options")
        if not isinstance(opts, list):
            errs.append("%s: options must be an array" % full)
            continue
        for o in opts:
            if (
                not isinstance(o, dict)
                or not isinstance(o.get("name"), str)
                or not o.get("name", "").startswith("--")
            ):
                errs.append("%s: bad option entry" % full)
            elif o.get("type") not in ("str", "int", "flag"):
                errs.append("%s: option %s bad type" % (full, o.get("name")))
        if not isinstance(c.get("target"), str) or not c.get("target"):
            errs.append("%s: target must be a non-empty string" % full)
    return errs


_CLI_SYSTEM = (
    "You are an expert Python architect. Design the click CLI command tree of a "
    "Python project from its specification. Output JSON with a \"commands\" "
    "array. Each command: "
    '{"group": ["<top group>", "<nested group>", ...], "name": "single lowercase '
    'token", "options": [{"name": "--flag", "required": bool, "type": "str"|"int"|"flag", '
    '"field": "exact service method param this option maps to (omit when the '
    'param name matches)"}], "target": "the exact service method name this '
    'command calls"}. Use the exact command surface and option names the spec '
    "names. The target must be "
    "one of the service methods already designed (never invent method names)."
)


def _design_cli(prompt_text, context, service_methods, verbose=False):
    """Design the CLI command tree; targets constrained to service methods."""
    schema = _cli_schema()
    allowed = {m.get("name") for m in service_methods if isinstance(m, dict)}
    user = (
        "SPECIFICATION:\n%s\n\n"
        "PROJECT LAYOUT SO FAR:\n%s\n\n"
        "AVAILABLE SERVICE METHODS (target must be one of these):\n%s\n\n"
        "Emit the CLI command JSON now."
        % (
            prompt_text,
            context,
            ", ".join(sorted(allowed)) if allowed else "(none yet)",
        )
    )
    messages = [
        {"role": "system", "content": _CLI_SYSTEM},
        {"role": "user", "content": user},
    ]
    for attempt in (0, 1):
        # 4096-token budget: an 11-command CLI design with option arrays
        # overflows the 2048 default mid-JSON -> truncated -> parse failure.
        data = _json_complete(
            messages, schema=schema, max_tokens=4096, verbose=verbose
        )
        if data is None:
            continue
        # Normalize near-miss command tokens before validation: specs write
        # hyphenated commands ("low-stock") while the schema demands
        # snake_case identifiers — normalize instead of rejecting.
        for c in data.get("commands") or []:
            if not isinstance(c, dict):
                continue
            if isinstance(c.get("name"), str):
                c["name"] = re.sub(r"[\s-]+", "_", c["name"].strip())
            grp = c.get("group")
            if isinstance(grp, list):
                c["group"] = [
                    re.sub(r"[\s-]+", "_", g.strip())
                    for g in grp if isinstance(g, str)
                ]
            # Options: specs/model emit bare names ("category") where click
            # needs "--category"; normalize instead of rejecting.
            opts = c.get("options")
            if isinstance(opts, list):
                for o in opts:
                    if isinstance(o, dict) and isinstance(o.get("name"), str):
                        n = re.sub(r"[\s_]+", "-", o["name"].strip().lstrip("-"))
                        if n:
                            o["name"] = "--" + n
            # Targets: tolerate "Service.method" / "module.Service.method"
            # spellings — the trailing identifier is the method name.
            tgt = c.get("target")
            if isinstance(tgt, str) and "." in tgt:
                c["target"] = tgt.split(".")[-1].strip()
        errs = _v_cli(data)
        # constrain targets to existing service methods (the renderer
        # collapses group[-1]==name and suffixes flat collisions on its own,
        # so no shape-level rejection is needed here)
        for c in data.get("commands") or []:
            if not isinstance(c, dict):
                continue
            if c.get("target") not in allowed:
                errs.append(
                    "target %r is not a designed service method" % c.get("target")
                )
        if not errs:
            return data
        if verbose:
            print("    [design] cli invalid: %s" % "; ".join(errs[:3]))
        retry_user = (
            user
            + "\n\nThe previous CLI design was rejected with these errors. Fix ONLY "
            + "these — do not change anything else:\n"
            + "\n".join("  - " + e for e in errs)
        )
        messages = [messages[0], {"role": "user", "content": retry_user}]
    print(
        "    [design] cli.py: FAILED (%s)"
        % ("; ".join(errs[:3]) if errs else "no valid JSON"),
        file=sys.stderr,
    )
    return None


def _design_module(path, kind, prompt_text, context, verbose=False):
    """One schema-constrained design call with one corrective retry."""
    schema = {
        "exceptions": _exceptions_schema,
        "models": _entities_schema,
        "repositories": _methods_schema,
        "services": _methods_schema,
    }[kind]()
    system = _DESIGN_SYSTEMS[kind]
    user = (
        "SPECIFICATION:\n%s\n\n"
        "PROJECT LAYOUT SO FAR:\n%s\n\n"
        "FILE TO DESIGN: %s\n"
        "Emit the JSON now."
        % (prompt_text, context, path)
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    validator = {
        "exceptions": _v_exceptions,
        "models": _v_entities,
        "repositories": lambda d: _v_methods(d, path),
        "services": lambda d: _v_methods(d, path),
    }[kind]

    for attempt in (0, 1):
        # 4096-token budget: method designs with many entries (11-command
        # CLIs, 8-method services) overflow the 2048 default mid-JSON ->
        # truncated output -> guaranteed design failure.
        data = _json_complete(
            messages, schema=schema, max_tokens=4096, verbose=verbose
        )
        if data is None:
            print("    [design] %s: no JSON (attempt %d)" % (path, attempt + 1))
            continue
        errs = validator(data)
        if errs and kind in ("services", "repositories", "models"):
            # Malformed optimization hints degrade gracefully instead of
            # failing the design: strip them and re-validate what remains.
            if kind == "models":
                stripped = _strip_invalid_list_filters(data)
                label = "invalid list_filter(s)"
            else:
                stripped = _strip_invalid_impls(data)
                label = "invalid impl(s)"
            if stripped:
                errs = validator(data)
                if not errs:
                    print("    [design] %s: dropped %d %s, accepted"
                          % (path, stripped, label))
                    return data
        if not errs:
            return data
        if verbose:
            print("    [design] %s invalid: %s (attempt %d)"
                  % (path, "; ".join(errs[:3]), attempt + 1))
        retry_user = (
            user
            + "\n\nThe previous design was rejected with these errors. Fix ONLY "
            + "these — do not change anything else:\n"
            + "\n".join("  - " + e for e in errs)
        )
        messages = [messages[0], {"role": "user", "content": retry_user}]
    return None


def _describe_design(kind, data):
    if kind == "exceptions":
        return ", ".join(data.get("exceptions", [])) or "(none)"
    if kind == "models":
        parts = []
        for ent in data.get("entities", []):
            fields = ", ".join(
                "%s:%s%s%s"
                % (
                    f.get("name"),
                    f.get("type", ""),
                    "*" if f.get("unique") else "",
                    "?" if f.get("nullable") else "",
                )
                for f in ent.get("fields", [])
            )
            parts.append("%s(%s)" % (ent.get("name", "?"), fields))
        return "; ".join(parts)
    return "; ".join(
        "%s(%s) -> %s"
        % (
            m.get("name"),
            ", ".join(
                p.get("name") + ":" + p.get("type", "") for p in m.get("params", [])
            ),
            m.get("returns"),
        )
        for m in data.get("methods", [])
    ) or "(none)"


def _fmt_design_context(designs):
    """Compact human-readable summary of the designs emitted so far."""
    lines = []
    for path, kind, data in designs:
        lines.append("  %s [%s]: %s" % (path, kind, _describe_design(kind, data)))
    return "\n".join(lines) if lines else "(none)"


# ---------------------------------------------------------------------------
# Deterministic renderers (smith phase2 pattern)
#
# Render mechanical files from the design manifest — never from raw prompt or
# from the LLM writing code. The LLM only fills business bodies (service
# methods + repository custom methods) inside locked skeletons.
# ---------------------------------------------------------------------------


def _snake(s):
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def _camel(s):
    return "".join(p.capitalize() for p in re.split(r"[_\s]+", s) if p)


def _plural(e):
    if e.endswith("y") and len(e) > 1 and e[-2] not in "aeiou":
        return e[:-1] + "ies"
    return e + "s"


def _bare(t):
    return (t or "").replace("Optional[", "").replace("]", "").strip()


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
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        ]
        if pairs:
            unique_map[name] = pairs
    if unique_map:
        const_lines = ["UNIQUE_TOGETHER: Dict[str, List[List[str]]] = {"]
        for cls, pairs in sorted(unique_map.items()):
            inner = ", ".join('("%s", "%s")' % tuple(p) for p in pairs)
            const_lines.append('    "%s": [%s],' % (cls, inner))
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


def _repo_method_body(m, ent, ent_snake, model):
    """Deterministic body lines for a designed custom repository method, or
    None (=> stub, then LLM fill).

    Fully declarative: a method carrying impl {"kind": "list_filtered"}
    delegates to the deterministic self.list(...) restricted to the
    entity's DECLARED list_filters. Methods without a resolvable impl stay
    locked stubs for _llm_fill. There are NO method-name patterns here —
    filter_by_date(), search_period(), find_X_by_Y all resolve through the
    same declaration.
    """
    impl = m.get("impl")
    if not isinstance(impl, dict) or impl.get("kind") != "list_filtered" or not ent:
        return None
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    # The deterministic list() accepts these DECLARED keyword filters only.
    valid = _filter_params(ent)
    args = [p for p in params if p in valid]
    if not args:
        return None
    lines = ["        return self.list("]
    lines += ["            %s=%s," % (p, p) for p in args]
    lines += ["        )"]
    return lines


def _repo_fill_ok(filled, design):
    """Accept an LLM repository fill only if every designed custom method
    survived the locked-skeleton edit (mirror of the service guard)."""
    if not filled:
        return False
    try:
        tree = ast.parse(filled)
    except SyntaxError:
        return False
    defined = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    required = {
        m.get("name") for m in (design.get("methods") or [])
        if isinstance(m, dict) and m.get("name")
    }
    return required.issubset(defined)


def _render_repository_file(ent_snake, design, entities_by_class, exception_names=None,
                            prompt_text="", verbose=False):
    """Deterministic CRUD repo over a Database object (database.py owns DDL).

    - create/get_by_id/get_all/update/delete are rendered with real bodies.
    - `list(**filters)` is built from the entity's declared "list_filters"
      design entries (param/column/op) — no suffix heuristics, no LLM.
    - a designed unique_together pair renders
      get_by_<a>_and_<b> and delete(a, b) replacing the id-based delete.
    - update raises "<Model>NotFoundError" when the row is missing, if that
      exception was designed (contract-style, deterministic).
    """
    model = _camel(ent_snake)
    repo = model + "Repository"
    ent = entities_by_class.get(model)
    if not ent:
        return ""
    exception_names = exception_names or []
    table_names = {cls: _entity_table_name(e) for cls, e in entities_by_class.items()}
    cols = _repo_columns(ent, table_names)
    nonid = [c for c in cols if not c[2]]
    col_names = [c[0] for c in nonid]
    table = table_names.get(model) or _plural(ent_snake)

    # --- declared filter API (from the entity design's list_filters) --------
    filter_specs = _declared_filters(ent)
    filter_params = [(p, None) for p, _, _ in filter_specs]
    _FRAG = {"eq": " AND %s = ?", "gte": " AND %s >= ?", "lte": " AND %s <= ?"}
    filter_where = [(_FRAG[op] % col, p) for p, col, op in filter_specs]

    # --- unique_together pair -> lookup + delete-by-pair --------------------
    unique_pairs = ent.get("unique_together") or []
    pair = None
    for up in unique_pairs:
        if isinstance(up, list) and len(up) == 2:
            pair = [str(u) for u in up]
            break
    not_found_exc = "%sNotFoundError" % model
    raise_missing = not_found_exc in exception_names

    insert_cols = ", ".join(col_names)
    placeholders = ", ".join("?" for _ in col_names)
    insert_vals = ", ".join("%s.%s" % (ent_snake, c) for c in col_names)

    L = []
    L.append('"""%s data access."""' % repo)
    L.append("from __future__ import annotations")
    L.append("")
    L.append("import sqlite3")
    L.append("from typing import Any, Dict, List, Optional")
    L.append("")
    L.append("from database import Database")
    L.append("from models import %s" % model)
    if raise_missing:
        L.append("from exceptions import %s" % not_found_exc)
    L.append("")
    L.append("")
    L.append("class %s:" % repo)
    L.append('    """SQLite repository for %s over the shared Database."""' % model)
    L.append("")
    L.append("    def __init__(self, db: Database) -> None:")
    L.append("        self.db = db")
    L.append("")
    L.append("    def create(self, %s: %s) -> int:" % (ent_snake, model))
    L.append("        with self.db.connect() as conn:")
    L.append("            cur = conn.cursor()")
    L.append("            cur.execute(")
    L.append('                "INSERT INTO %s (%s) VALUES (%s)",' % (table, insert_cols, placeholders))
    L.append("                (%s)," % insert_vals)
    L.append("            )")
    L.append("            conn.commit()")
    L.append("            return cur.lastrowid")
    L.append("")
    L.append("    def get_by_id(self, id: int) -> Optional[%s]:" % model)
    L.append("        with self.db.connect() as conn:")
    L.append("            row = conn.execute(")
    L.append('                "SELECT * FROM %s WHERE id = ?", (id,)' % table)
    L.append("            ).fetchone()")
    L.append("            return %s(**dict(row)) if row else None" % model)
    L.append("")
    L.append("    def get_all(self) -> List[%s]:" % model)
    L.append("        with self.db.connect() as conn:")
    L.append("            rows = conn.execute(")
    L.append('                "SELECT * FROM %s ORDER BY id"' % table)
    L.append("            ).fetchall()")
    L.append("            return [%s(**dict(r)) for r in rows]" % model)
    L.append("")
    if filter_params:
        sig = ", ".join("%s: Optional[Any] = None" % p[0] for p in filter_params)
        L.append("    def list(self, %s) -> List[%s]:" % (sig, model))
        L.append("        with self.db.connect() as conn:")
        L.append('            query = "SELECT * FROM %s WHERE 1=1"' % table)
        L.append("            params: List[Any] = []")
        for frag, expr in filter_where:
            L.append("            if %s is not None:" % expr)
            L.append("                query += %r" % frag)
            L.append("                params.append(%s)" % expr)
        L.append("            rows = conn.execute(query + \" ORDER BY id\", params).fetchall()")
        L.append("            return [%s(**dict(r)) for r in rows]" % model)
    else:
        L.append("    def list(self) -> List[%s]:" % model)
        L.append("        return self.get_all()")
    L.append("")
    if pair:
        a, b = pair
        # Strip the "_id" suffix for the method name (<col>_id -> <col>);
        # the SQLite WHERE clause keeps the real column name.
        a_fn = a[:-3] if a.endswith("_id") else a
        b_fn = b[:-3] if b.endswith("_id") else b
        L.append("    def get_by_%s_and_%s(self, %s: Any, %s: Any) -> Optional[%s]:"
                 % (a_fn, b_fn, a, b, model))
        L.append("        with self.db.connect() as conn:")
        L.append("            row = conn.execute(")
        L.append('                "SELECT * FROM %s WHERE %s = ? AND %s = ?", (%s, %s)'
                 % (table, a, b, a, b))
        L.append("            ).fetchone()")
        L.append("            return %s(**dict(row)) if row else None" % model)
        L.append("")
    L.append("    def update(self, id: int, data: Dict[str, Any]) -> bool:")
    L.append("        if not data:")
    L.append("            return False")
    L.append("        allowed = %r" % (col_names,))
    L.append("        sets = [k for k in data if k in allowed]")
    L.append("        if not sets:")
    L.append("            return False")
    L.append("        with self.db.connect() as conn:")
    L.append("            cur = conn.cursor()")
    L.append("            cur.execute(")
    # build the SET clause at RUNTIME inside the generated function where
    # `sets` exists — never at render time (renderer has no `sets`).
    # .format is used here so `%` in the generated source is not mangled.
    L.append('                "UPDATE {table} SET " + ", ".join("%s = ?" % k for k in sets) + " WHERE id = ?",'.format(table=table))
    L.append("                [data[k] for k in sets] + [id],")
    L.append("            )")
    L.append("            conn.commit()")
    L.append("            if cur.rowcount == 0:")
    if raise_missing:
        L.append("                raise %s(id)" % not_found_exc)
    else:
        L.append("                return False")
    L.append("            return True")
    L.append("")
    if pair:
        a, b = pair
        L.append("    def delete(self, %s: Any, %s: Any) -> bool:" % (a, b))
        L.append("        with self.db.connect() as conn:")
        L.append("            cur = conn.cursor()")
        L.append("            cur.execute(")
        L.append('                "DELETE FROM %s WHERE %s = ? AND %s = ?", (%s, %s)'
                 % (table, a, b, a, b))
        L.append("            )")
        L.append("            conn.commit()")
        L.append("            return cur.rowcount > 0")
    else:
        L.append("    def delete(self, id: int) -> bool:")
        L.append("        with self.db.connect() as conn:")
        L.append("            cur = conn.cursor()")
        L.append("            cur.execute(")
        L.append('                "DELETE FROM %s WHERE id = ?", (id,)' % table)
        L.append("            )")
        L.append("            conn.commit()")
        L.append("            return cur.rowcount > 0")
    L.append("")
    # custom designed methods: deterministic recipes where recognized, else
    # locked stubs (class methods, 1 indent unit) for the LLM fill.
    stub_methods = []
    for m in design.get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        body = _repo_method_body(m, ent, ent_snake, model)
        if body is not None:
            def_line = _method_stub_code(m, 1).split("\n")[0]
            L.append(def_line)
            L.extend(body)
            L.append("")
        else:
            L.append(_method_stub_code(m, 1))
            L.append("")
            stub_methods.append(m)
    deterministic = "\n".join(L).rstrip() + "\n"
    if not prompt_text or not stub_methods:
        return deterministic
    # Same contract as services: the LLM fills only the remaining stubs, and
    # the result is accepted only if every designed custom method survived.
    filled = _llm_fill("repository", "", deterministic, prompt_text, verbose=verbose)
    if not filled:
        return deterministic
    if not _repo_fill_ok(filled, design):
        if verbose:
            print("    [fill] repository: rejected (signature mismatch)")
        return deterministic
    return filled


def _sanitize_type_hint(t):
    """Normalize LLM pseudo-type hints into valid Python type expressions.

    - `int?` / `datetime.date?` -> `Optional[int]` / `Optional[datetime.date]`
    - `int | None` -> `Optional[int]`
    - `Task?` / `Task | None` -> `Optional[Task]`
    - `Dict[str, any]` -> `Dict[str, Any]`
    - `List[Item]`, `str`, `bool`, `Any` pass through
    """
    t = (t or "").strip()
    if not t:
        return "Any"
    if t.endswith("?"):
        return "Optional[" + _sanitize_type_hint(t[:-1]) + "]"
    if t == "any":
        return "Any"
    if t == "None":
        return "None"
    if "|" in t:
        parts = [p.strip() for p in t.split("|")]
        parts = [_sanitize_type_hint(p) for p in parts]
        if "None" in parts:
            inner = [p for p in parts if p != "None"]
            return "Optional[%s]" % (inner[0] if len(inner) == 1 else "Union[%s]" % ", ".join(inner))
        return "Union[%s]" % ", ".join(parts)
    # Recurse into generics
    for base in ("List[", "Dict[", "Optional[", "Union["):
        if t.startswith(base) and t.endswith("]"):
            inner = t[len(base) : -1]
            # split on top-level commas only
            parts = []
            depth = 0
            cur = []
            for ch in inner:
                if ch in "[(":
                    depth += 1
                elif ch in "])":
                    depth -= 1
                if ch == "," and depth == 0:
                    parts.append("".join(cur).strip())
                    cur = []
                else:
                    cur.append(ch)
            if cur:
                parts.append("".join(cur).strip())
            mapped = [_sanitize_type_hint(p) for p in parts]
            return base[:-1] + "[%s]" % ", ".join(mapped)
    return t


def _method_stub_code(m, indent=4):
    """def line for a design method; body = NotImplementedError.

    Parameter order is preserved, but once an Optional param is seen every
    following param is defaulted (`= None`) so the signature never violates
    Python's "non-default follows default" rule.
    """
    name = m.get("name")
    params = m.get("params") or []
    sig_parts = []
    seen_optional = False
    for p in params:
        ptype = _sanitize_type_hint(p.get("type") or "")
        if ptype.startswith("Optional["):
            seen_optional = True
            sig_parts.append("%s: %s = None" % (p["name"], ptype))
        elif seen_optional:
            sig_parts.append("%s: %s = None" % (p["name"], ptype))
        elif ptype.startswith("List[") or ptype.startswith("Dict["):
            sig_parts.append("%s: %s" % (p["name"], ptype))
        else:
            sig_parts.append("%s: %s" % (p["name"], ptype))
    sig = ", ".join(sig_parts)
    if sig:
        sig = "self, " + sig
    else:
        sig = "self"
    ret = _sanitize_type_hint(m.get("returns") or "None")
    return '    ' * indent + "def %s(%s) -> %s:\n%s    raise NotImplementedError()" % (
        name, sig, ret, "    " * indent,
    )


# --- LLM fill for business bodies (service + repo custom methods) -----------

def _llm_fill(path, instruction, skeleton, prompt_text, verbose=False):
    """One LLM call: fill skeleton bodies, keep signatures/imports exact.

    Returns the full file text or None. Two attempts with corrective retry
    on compile failure.
    """
    user = instruction + "\n\nSKELETON:\n```python\n" + skeleton + "\n```"
    messages = [
        {
            "role": "system",
            "content": (
                "You are a meticulous senior Python engineer. You produce "
                "complete, runnable, dependency-correct code and you NEVER "
                "change signatures, class names, or imports you are told to keep."
            ),
        },
        {"role": "user", "content": user},
    ]
    for attempt in range(2):
        raw = _chat_completion(messages, max_tokens=LLM_MAX_TOKENS_LONG)
        body = _extract_code_block(raw)
        if body and _compiles(body):
            return body + "\n"
        if verbose:
            print("    [fill] %s: output rejected (attempt %d)" % (path, attempt + 1))
        messages = messages + [
            {"role": "assistant", "content": raw},
            {
                "role": "user",
                "content": (
                    "The previous output did not compile or kept the structure. "
                    "Re-emit the COMPLETE corrected file in a single "
                    "```python ... ``` block, keeping every class name, method "
                    "signature and import line exactly as in the skeleton."
                ),
            },
        ]
    return None


def _compiles(text):
    try:
        compile(text, "<llm>", "exec")
        return True
    except SyntaxError:
        return False


def _service_context(designs, entities_by_class):
    """A compact layout context for the service fill prompt."""
    lines = []
    for path, kind, data in designs:
        if kind == "repositories" or kind == "services":
            lines.append("  %s: %s" % (path, _describe_design(kind, data)))
    lines.append("  MODELS: %s" % _describe_design("models", {"entities": list(entities_by_class.values())}))
    return "\n".join(lines) or "(none)"


def _entity_design(entities_by_class, name):
    """The design dict for `name`, or None."""
    ent = entities_by_class.get(name)
    return ent if isinstance(ent, dict) else None


def _declared_filters(ent):
    """[(param, column, op)] exactly as the entity design declared them.

    The repository's list() API is built from this declaration alone — no
    suffix conventions, no field-name heuristics anywhere.
    """
    out = []
    for spec in ent.get("list_filters") or []:
        if (
            isinstance(spec, dict)
            and isinstance(spec.get("param"), str) and spec["param"]
            and isinstance(spec.get("column"), str) and spec["column"]
        ):
            out.append((spec["param"], spec["column"], spec.get("op", "eq")))
    return out


def _filter_params(ent):
    """Declared list() filter parameter names, in declaration order."""
    return [p for p, _, _ in _declared_filters(ent)]


def _csv_chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def _impl_bindings_ok(impl, m, entities_by_class):
    """Cross-check an impl's references against the DESIGNED entities.

    Returns (class_name, ent_design) when every binding resolves against an
    existing entity and the method's own params; otherwise (None, None) so
    the caller degrades to CRUD delegation / a locked stub deterministically.
    """
    kind = impl.get("kind")
    # Placement guard: the impl's implied output shape must match the
    # DESIGNED return type — totals/groups aggregate into a Dict, CSV
    # export writes a file (None/str). This rejects impls attached to
    # listing/CRUD methods (List[Entity] / None returns) without any
    # method-name or domain heuristics.
    returns = m.get("returns") or ""
    if kind == "export_csv":
        if (
            returns and returns != "None"
            and "str" not in returns and "Path" not in returns
        ):
            return None, None
    elif kind == "below_foreign_threshold":
        # row listing below a related-entity threshold: must return a List
        if returns and "List" not in returns and "list" not in returns:
            return None, None
    else:
        # totals/groups may return an aggregate Dict OR a bare numeric
        # scalar (the handler adapts its output shape to the designed
        # return type); anything else (List[Entity], None, ...) means the
        # impl is misplaced on a listing/CRUD method.
        has_dict = "Dict" in returns or "dict" in returns
        numeric = "int" in returns.lower() or "float" in returns.lower()
        if not has_dict and not numeric:
            return None, None
    name = impl.get("entity") or ""
    ent = entities_by_class.get(_camel(name))
    if not isinstance(ent, dict) and name.endswith("s"):
        # tolerate a pluralized entity reference from the design
        ent = entities_by_class.get(_camel(name[:-1]))
    if not isinstance(ent, dict):
        return None, None
    fields = {
        f.get("name") for f in (ent.get("fields") or [])
        if isinstance(f, dict)
    }
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    field_keys = {
        "total_in_period": ("value_field", "date_field"),
        "total_filtered": ("value_field",),
        "export_csv": (),
        "duplicate_groups": (),
        "sum_by_group": ("value_field",),
        "below_foreign_threshold": ("value_field", "fk_field"),
    }.get(kind)
    if field_keys is None:
        return None, None
    for key in field_keys:
        if impl.get(key) not in fields:
            return None, None
    param_keys = {
        "total_in_period": ("period_param",),
        "export_csv": ("file_param",),
    }
    for key in param_keys.get(kind, ()):
        if impl.get(key) not in params:
            return None, None
    gb = impl.get("group_by")
    if kind in ("duplicate_groups", "sum_by_group"):
        if not isinstance(gb, list) or not gb or any(g not in fields for g in gb):
            return None, None
    if kind == "below_foreign_threshold":
        # Cross-entity bindings must resolve against DESIGNED entities too:
        # the referenced entity must exist and own the threshold field.
        ref_ent = entities_by_class.get(_camel(impl["ref_entity"]))
        if not isinstance(ref_ent, dict):
            return None, None
        ref_fields = {
            f.get("name") for f in (ref_ent.get("fields") or [])
            if isinstance(f, dict)
        }
        if impl["ref_field"] not in ref_fields:
            return None, None
    return _camel(impl["entity"]), ent


def _h_total_in_period(m, impl, ent, entities_by_class):
    """Sum value_field over one month/year bucket of date_field."""
    var = _snake(impl["entity"])
    vf, df = impl["value_field"], impl["date_field"]
    pp, gran = impl["period_param"], impl["granularity"]
    rk = impl.get("result_key") or "total"
    # The generated repo list() only accepts DECLARED filter params: find
    # the declared gte/lte pair over date_field.
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
        # designed scalar return: yield the bare total
        return rows_lines + ["        return sum(e.%s for e in rows)" % vf]
    return rows_lines + [
        "        total = sum(e.%s for e in rows)" % vf,
        "        return {'%s': %s, '%s': total}" % (pp, pp, rk),
    ]


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
        # designed scalar return: yield the bare total
        return head + ["        return sum(e.%s for e in rows)" % vf]
    return head + [
        "        total = sum(e.%s for e in rows)" % vf,
        "        return {'%s': total}" % rk,
    ]


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


def _h_sum_by_group(m, impl, ent, entities_by_class):
    """Sum value_field grouped by the declared fields -> {group: total}."""
    var = _snake(impl["entity"])
    vf = impl["value_field"]
    gb = list(impl["group_by"])
    declared = set(_filter_params(ent))
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    kwargs = [p for p in params if p in declared]
    args = ", ".join("%s=%s" % (p, p) for p in kwargs)
    call = "self.%s_repo.list(%s)" % (var, args)
    lines = ["        results = {}"]
    if len(gb) == 1:
        lines += [
            "        for row in %s:" % call,
            "            key = row.%s" % gb[0],
        ]
    else:
        key_tuple = ", ".join("row.%s" % g for g in gb)
        lines += [
            "        for row in %s:" % call,
            "            key = (%s)" % key_tuple,
        ]
    lines += [
        "            results[key] = results.get(key, 0) + row.%s" % vf,
        "        return results",
    ]
    return lines


def _h_below_foreign_threshold(m, impl, ent, entities_by_class):
    """Rows whose value_field is strictly below the related entity's
    threshold field (joined through the FK), e.g.
    product.stock_qty < product.category.reorder_threshold."""
    var = _snake(impl["entity"])
    ref_var = _snake(_camel(impl["ref_entity"]))
    vf, ff, fk = impl["value_field"], impl["ref_field"], impl["fk_field"]
    return [
        "        results = []",
        "        thresholds = {}",
        "        for ref_row in self.%s_repo.get_all():" % ref_var,
        "            if ref_row.%s is not None:" % ff,
        "                thresholds[ref_row.id] = ref_row.%s" % ff,
        "        for row in self.%s_repo.list():" % var,
        "            threshold = thresholds.get(row.%s)" % fk,
        "            if threshold is not None and row.%s < threshold:" % vf,
        "                results.append(row)",
        "        return results",
    ]


_IMPL_HANDLERS = {
    "total_in_period": _h_total_in_period,
    "total_filtered": _h_total_filtered,
    "export_csv": _h_export_csv,
    "duplicate_groups": _h_duplicate_groups,
    "sum_by_group": _h_sum_by_group,
    "below_foreign_threshold": _h_below_foreign_threshold,
}


def _zero_param_dict_repo_customs(designs, entities_by_class):
    """[(entity_snake, method_name)] of DESIGNED repository custom methods
    that take no params and return a Dict — aggregate-shaped. Feeds the
    unique-shape service delegation (never name-based)."""
    known = {_snake(c) for c in entities_by_class}
    out = []
    for path, kind, data in designs or []:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        if ent_snake not in known:
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            params = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict)
            ]
            ret = m.get("returns") or ""
            if not params and "dict" in ret.lower():
                out.append((ent_snake, m["name"]))
    return out


def _service_method_body(m, entities_by_class, exception_names, repo_customs=None):
    """Deterministic body lines for a service method, or None (=> stub).

    Fully declarative: a designed method may carry an `impl` object naming
    the entity/fields/params its body operates on; generic handlers render
    the body from those declarations alone. There are NO method-name
    patterns, NO field-suffix heuristics, and NO domain vocabulary here.
    Methods without a resolvable impl fall through to unique-shape
    aggregate delegation, then generic CRUD delegation
    (add_/list_/get_/update_/delete_<entity> convention), then to a locked
    stub for the LLM fill phase.
    """
    impl = m.get("impl")
    if isinstance(impl, dict):
        handler = _IMPL_HANDLERS.get(impl.get("kind"))
        if handler is not None:
            cls, ent = _impl_bindings_ok(impl, m, entities_by_class)
            if cls is not None:
                lines = handler(m, impl, ent, entities_by_class)
                if lines is not None:
                    return lines
    # Unique-shape aggregate delegation: a zero-param Dict-returning service
    # method with no impl delegates to THE unique zero-param Dict-returning
    # repository custom across the whole design (shape-matched, never by
    # name). More than one candidate => ambiguous => degrade to the generic
    # tiers instead of guessing.
    if (
        repo_customs
        and len(repo_customs) == 1
        and not (m.get("params") or [])
        and "dict" in (m.get("returns") or "").lower()
    ):
        ent_snake, meth = repo_customs[0]
        return ["        return self.%s_repo.%s()" % (ent_snake, meth)]
    return _generic_service_delegation(m, entities_by_class, exception_names)


def _generic_service_delegation(m, entities_by_class, exception_names=None):
    """Tier-2 deterministic CRUD delegation for any entity.

    Handles add_<entity>, list_<entity> / get_<entity>_by_id /
    update_<entity> / delete_<entity> against the deterministic repository
    API. Only the repository's derived filter params are passed to list();
    everything else stays a stub for the LLM fill phase. add_<entity> builds
    the entity from the method params and inserts through the repository's
    deterministic `create` (never `.add`/`.insert` — the 4B model has been
    caught hallucinating those). Entities handled by Tier 1 are skipped here.
    """
    exception_names = exception_names or []
    name = m.get("name") or ""
    params = [(p.get("name"), p.get("type")) for p in (m.get("params") or [])
              if isinstance(p, dict) and p.get("name")]
    param_names = [p for p, _ in params]
    for ent_name, ent in entities_by_class.items():
        var = _snake(ent_name)
        fields = {f.get("name") for f in (ent.get("fields") or [])}
        # Mirror the deterministic repo list() filters (declared list_filters).
        filters = _filter_params(ent)

        if name in ("add_" + var, "create_" + var):
            kwargs = ["%s=%s" % (p, p) for p in param_names if p in fields]
            if not kwargs:
                return None
            # Required (non-nullable, non-id) fields not covered by params:
            # only fields DECLARED auto:"now" are stamped deterministically;
            # anything else means real business logic -> leave a stub.
            covered = {p for p in param_names if p in fields}
            # Only date/datetime-typed non-id fields may be stamped at
            # creation: stamping an id or a bool/str field with a timestamp
            # corrupts the row (the 4B model declares auto:"now" on random
            # fields).
            auto_now = {
                f.get("name")
                for f in (ent.get("fields") or [])
                if isinstance(f, dict) and f.get("auto") == "now"
                and f.get("name") != "id"
                and f.get("type") in ("date", "datetime")
            }
            required = {
                f.get("name") for f in (ent.get("fields") or [])
                if not f.get("nullable") and f.get("name") != "id"
            }
            missing = required - covered
            if missing - auto_now:
                return None
            for af in sorted(auto_now - covered):
                kwargs.append("%s=datetime.datetime.now().isoformat()" % af)
            lines = []
            # Generic FK validation: for any designed param that is a
            # foreign-key column of this entity (<x>_id), when the referenced
            # entity <X> exists AND a <X>NotFoundError was designed, emit a
            # deterministic existence check. Fully design-driven.
            fk_params = [
                p for p in param_names
                if p.endswith("_id") and p != "id" and p in fields
            ]
            for fk in fk_params:
                ref_cls = _camel(fk[: -len("_id")])
                not_found = "%sNotFoundError" % ref_cls
                if (
                    ref_cls in entities_by_class
                    and not_found in exception_names
                    and "%s_repo" % _snake(ref_cls) != "%s_repo" % var
                ):
                    lines.append("        if %s is not None:" % fk)
                    lines.append(
                        "            if self.%s_repo.get_by_id(%s) is None:"
                        % (_snake(ref_cls), fk)
                    )
                    lines.append("                raise %s(%s)" % (not_found, fk))
            lines.append("        %s = %s(%s)" % (var, ent_name, ", ".join(kwargs)))
            lines.append("        return self.%s_repo.create(%s)" % (var, var))
            return lines
        if name in ("list_" + var, "list_" + _plural(var)):
            kw = [p for p in param_names if p in filters]
            call = ", ".join("%s=%s" % (p, p) for p in kw)
            return ["        return self.%s_repo.list(%s)" % (var, call)]
        if name == "get_%s_by_id" % var:
            idp = param_names[0] if param_names else "id"
            return ["        return self.%s_repo.get_by_id(%s)" % (var, idp)]
        if name == "update_%s" % var:
            idp = param_names[0] if param_names else "id"
            if "data" in param_names:
                return ["        self.%s_repo.update(%s, data)" % (var, idp)]
            # Designed signature carries field params (e.g. update_task(id,
            # title, ...)): build the dict for the deterministic repo API,
            # dropping fields the caller left as None so the repo never
            # overwrites columns with NULL (NOT NULL constraint).
            rest = [p for p in param_names[1:] if p in fields]
            mapping = ", ".join("'%s': %s" % (p, p) for p in rest)
            return [
                "        data = {k: v for k, v in {%s}.items() if v is not None}" % mapping,
                "        return self.%s_repo.update(%s, data)" % (var, idp),
            ]
        if name == "delete_%s" % var:
            idp = param_names[0] if param_names else "id"
            return ["        return self.%s_repo.delete(%s)" % (var, idp)]
    return None


def _apply_filter_floors(entities_by_class, designs):
    """Deterministic floor for entity list_filters, derived ONLY from the
    designed method signatures — never from prompt text or field-name
    suffixes:

    - a designed parameter whose name equals a non-id field of the entity
      becomes an equality filter for that column;
    - a designed start_<x>/end_<x> parameter pair becomes a gte/lte range
      over the entity's only date/datetime-typed field, when exactly one
      such field exists.

    Declared list_filters always win; floors only fill gaps so the
    repository list() API covers the parameters the designed service and
    repository methods actually take.
    """
    uniq = []
    seen = set()
    for path, kind, data in designs:
        if kind not in ("repositories", "services") or not isinstance(data, dict):
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict):
                continue
            for p in m.get("params") or []:
                if isinstance(p, dict) and p.get("name") and p["name"] not in seen:
                    seen.add(p["name"])
                    uniq.append(p["name"])
    uniq_set = set(uniq)
    start_sufs = {p[6:] for p in uniq if p.startswith("start_") and len(p) > 6}
    end_sufs = {p[4:] for p in uniq if p.startswith("end_") and len(p) > 4}
    range_sufs = sorted(start_sufs & end_sufs)

    for ent in entities_by_class.values():
        fields = {
            f.get("name"): f
            for f in (ent.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        }
        lf = [
            s for s in (ent.get("list_filters") or [])
            if isinstance(s, dict) and s.get("param")
        ]
        declared = {s["param"] for s in lf}
        covered_ops = {(s.get("column"), s.get("op")) for s in lf}

        for fname in sorted(fields):
            if fname != "id" and fname in uniq_set and fname not in declared:
                lf.append({"param": fname, "column": fname, "op": "eq"})
                declared.add(fname)

        date_cols = [
            n for n in sorted(fields)
            if fields[n].get("type") in ("date", "datetime")
        ]

        def _resolve_range_col(suf):
            """Date column for a start_<x>/end_<x> suffix: exact field-name
            match first, then unique '<col>_<suffix>' match, else the unique
            date column. Works for multi-date entities where the suffix
            disambiguates (start_date/end_date -> expense_date)."""
            exact = [c for c in date_cols if c == suf]
            if len(exact) == 1:
                return exact[0]
            suffixed = [c for c in date_cols if c.endswith("_" + suf)]
            if len(suffixed) == 1:
                return suffixed[0]
            if len(date_cols) == 1:
                return date_cols[0]
            return None

        for suf in range_sufs:
            pa, pb = "start_" + suf, "end_" + suf
            if pa in declared or pb in declared:
                continue
            col = _resolve_range_col(suf)
            if col is None:
                continue
            if (col, "gte") in covered_ops or (col, "lte") in covered_ops:
                continue
            lf.append({"param": pa, "column": col, "op": "gte"})
            lf.append({"param": pb, "column": col, "op": "lte"})
            declared.update((pa, pb))
        ent["list_filters"] = lf


def _apply_impl_floors(entities_by_class, designs):
    """Deterministic floor for declarative service impls, derived ONLY from
    the designed signatures and entity shapes — no method-name patterns,
    no domain vocabulary:

    - period total: a Dict-returning method whose params are exactly one
      scalar that is NOT a declared list_filter of the (unique) entity
      having exactly one date-typed and one numeric field. A str period
      binds to a month bucket ("YYYY-MM"), an int period to a year bucket.
    - filtered total: a Dict-returning method whose params all match the
      candidate entity's declared list_filters.

    Only fills gaps: methods already carrying a valid impl are untouched.
    """
    for path, kind, data in designs:
        if kind != "services" or not isinstance(data, dict):
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or m.get("impl") is not None:
                continue
            returns = m.get("returns") or ""
            low_ret = returns.lower()
            if (
                "Dict" not in returns and "dict" not in returns
                and "int" not in low_ret and "float" not in low_ret
            ):
                continue
            params = [
                p.get("name")
                for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            # unique aggregate-capable entity: exactly one date + one numeric
            cands = []
            for cls_, ent_ in entities_by_class.items():
                flds = [
                    f for f in (ent_.get("fields") or [])
                    if isinstance(f, dict) and f.get("name") and f["name"] != "id"
                ]
                dates = [f["name"] for f in flds
                         if f.get("type") in ("date", "datetime")]
                # exclude foreign keys: an FK column is an int but is never
                # the aggregate target of a total
                nums = [
                    f["name"] for f in flds
                    if f.get("type") in ("int", "float")
                    and not f["name"].endswith("_id")
                ]
                if len(dates) == 1 and len(nums) == 1:
                    cands.append((cls_, ent_, dates[0], nums[0]))
            dcol = None
            if len(cands) == 1:
                cls, ent, dcol, ncol = cands[0]
            else:
                # Relaxed fallback: exactly ONE numeric-non-FK entity whose
                # DECLARED filter set covers every method param -> a pure
                # filtered total (no period bucketing). Handles entities
                # with several date fields where the strict shape test
                # finds no unique candidate.
                hits = []
                for cls_, ent_ in entities_by_class.items():
                    flds = [
                        f for f in (ent_.get("fields") or [])
                        if isinstance(f, dict) and f.get("name") and f["name"] != "id"
                    ]
                    nums = [
                        f["name"] for f in flds
                        if f.get("type") in ("int", "float")
                        and not f["name"].endswith("_id")
                    ]
                    if len(nums) != 1:
                        continue
                    fparams = {
                        s.get("param")
                        for s in (ent_.get("list_filters") or [])
                        if isinstance(s, dict) and s.get("param")
                    }
                    if params and set(params) <= fparams:
                        hits.append((cls_, ent_, nums[0]))
                if len(hits) != 1:
                    continue
                cls, ent, ncol = hits[0]
            declared = {
                s.get("param")
                for s in (ent.get("list_filters") or [])
                if isinstance(s, dict)
            }
            nonfilter = [p for p in params if p not in declared]
            if len(params) == 1 and len(nonfilter) == 1:
                ptype = next(
                    (q.get("type", "") for q in m.get("params") or []
                     if isinstance(q, dict) and q.get("name") == params[0]),
                    "",
                )
                m["impl"] = {
                    "kind": "total_in_period",
                    "entity": _snake(cls),
                    "value_field": ncol,
                    "date_field": dcol,
                    "period_param": params[0],
                    "granularity": "year" if "int" in ptype.lower() else "month",
                    "result_key": "total",
                }
            elif params and len(nonfilter) == 0:
                m["impl"] = {
                    "kind": "total_filtered",
                    "entity": _snake(cls),
                    "value_field": ncol,
                    "result_key": "total",
                }

    # Repository floor: a custom repo method whose params ALL map to the
    # entity's DECLARED list_filters is a pure filtered listing — attach
    # impl {"kind": "list_filtered"} so its body renders deterministically.
    # This replaces every find_*_by_* / by_date_range name heuristic.
    for path, kind, data in designs:
        if kind != "repositories" or not isinstance(data, dict):
            continue
        stem = Path(path).stem
        ent_snake = (
            stem[: -len("_repository")] if stem.endswith("_repository") else stem
        )
        ent = entities_by_class.get(_camel(ent_snake))
        if not isinstance(ent, dict):
            continue
        valid = set(_filter_params(ent))
        if not valid:
            continue
        for m in data.get("methods") or []:
            if not isinstance(m, dict) or m.get("impl") is not None:
                continue
            # Only LISTING-shaped methods (List[...] / unspecified return):
            # a count/scalar custom query must stay a stub for the LLM fill.
            returns = m.get("returns") or ""
            if returns and "list" not in returns.lower():
                continue
            params = [
                p.get("name") for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
            if params and all(p in valid for p in params):
                m["impl"] = {"kind": "list_filtered"}


def _service_repo_interface(entities_by_class, designs):
    """{repo_attr: {method: [param names]}} exactly as _render_repository_file
    emits them: base CRUD + unique_together lookup + designed customs.

    Lets the service fill be validated mechanically so an LLM-filled body
    can never call a repo method that does not exist or pass the wrong
    number of arguments.
    """
    repo_designs = {}
    for path, kind, data in designs:
        if kind == "repositories" and isinstance(data, dict):
            repo_designs[Path(path).stem] = data
    interface = {}
    for ent in entities_by_class.values():
        ent_snake = _snake(ent["name"])
        attr = ent_snake + "_repo"
        # Entries are (param name, required) so the fill validator can
        # enforce that every REQUIRED param is covered by a call.
        methods = {
            "create": [("_obj", True)],
            "get_by_id": [("id", True)],
            "get_all": [],
            "list": ["_filters"],
            "update": [("id", True), ("data", True)],
            "delete": [("id", True)],
        }
        for up in ent.get("unique_together") or []:
            if isinstance(up, list) and len(up) == 2:
                a, b = [str(u) for u in up]
                a_fn = a[:-3] if a.endswith("_id") else a
                b_fn = b[:-3] if b.endswith("_id") else b
                methods["get_by_%s_and_%s" % (a_fn, b_fn)] = [(a, True), (b, True)]
        rdes = repo_designs.get(ent_snake + "_repository")
        if rdes:
            for m in rdes.get("methods") or []:
                if isinstance(m, dict) and m.get("name"):
                    params = []
                    for p in m.get("params") or []:
                        if isinstance(p, dict) and p.get("name"):
                            ptype = p.get("type") or ""
                            params.append(
                                (p["name"], not ptype.startswith("Optional"))
                            )
                    methods[m["name"]] = params
        interface[attr] = methods
    return interface


_DICT_METHODS = {
    "get", "keys", "values", "items", "copy", "update",
    "setdefault", "pop", "popitem", "clear",
}


def _service_type_context(entities_by_class, designs):
    """Designed-type information for semantic fill validation.

    entity_fields: {class_name: set(valid field names incl. id)} — entity
      constructor kwargs and instance attribute reads are checked against
      these.
    repo_returns: {(repo_attr, method): tag} derived from the DESIGNED
      repository return types: ("entity", Class), ("list", Class),
      ("dict",) — absent when the return type carries no checkable shape.
    """
    entity_fields = {}
    for cls, ent in entities_by_class.items():
        fields = {"id"}
        for f in ent.get("fields") or []:
            if isinstance(f, dict) and f.get("name"):
                fields.add(f["name"])
        entity_fields[cls] = fields

    repo_designs = {}
    for path, kind, data in designs or []:
        if kind == "repositories" and isinstance(data, dict):
            repo_designs[Path(path).stem] = data

    def _tag(returns):
        r = (returns or "").strip()
        low = r.lower()
        for cls in entity_fields:
            if re.search(r"\b%s\b" % cls, r):
                return ("list", cls) if "list" in low else ("entity", cls)
        if "dict" in low:
            return ("dict",)
        return None

    repo_returns = {}
    for ent in entities_by_class.values():
        attr = _snake(ent["name"]) + "_repo"
        rdes = repo_designs.get(_snake(ent["name"]) + "_repository")
        if not rdes:
            continue
        for m in rdes.get("methods") or []:
            if isinstance(m, dict) and m.get("name"):
                t = _tag(m.get("returns"))
                if t:
                    repo_returns[(attr, m["name"])] = t
    return {"entity_fields": entity_fields, "repo_returns": repo_returns}


def _semantic_fill_violations(tree, type_ctx):
    """Semantic checks over an LLM service fill using DESIGNED types only:

    (1) An entity constructor call may only pass declared field names —
        Expense(amount=...) when the model declares amount_cents is a
        guaranteed TypeError at runtime.
    (2) A variable assigned from a repo call whose designed return is an
        entity may only access declared fields (product.stock vs the
        declared stock_qty).
    (3) A variable assigned from a Dict-returning repo call must not be
        attribute-accessed (budget_status.spending on a plain dict).
    """
    entity_fields = type_ctx["entity_fields"]
    repo_returns = type_ctx["repo_returns"]

    def _repo_call_key_tag(call):
        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Attribute)
            and isinstance(call.func.value.value, ast.Name)
            and call.func.value.value.id == "self"
            and call.func.value.attr.endswith("_repo")
        ):
            return None
        key = (call.func.value.attr, call.func.attr)
        return key, repo_returns.get(key)

    dict_keys = type_ctx.get("dict_keys") or {}

    # pass 1b: designed parameter types from the skeleton signatures —
    # lets us catch guaranteed TypeErrors like date + str concatenation.
    param_types = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in node.args.args:
                if arg.arg == "self" or arg.annotation is None:
                    continue
                try:
                    param_types[arg.arg] = ast.unparse(arg.annotation).lower()
                except Exception:
                    param_types[arg.arg] = ""

    # pass 1: variable types from repo-call assignments and iterations
    var_types = {}
    var_keys = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            hit = _repo_call_key_tag(node.value)
            if hit:
                (attr, meth), tag = hit
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name):
                        var_types[tgt.id] = tag
                        keys = dict_keys.get((attr, meth))
                        if keys:
                            var_keys[tgt.id] = keys
        elif isinstance(node, ast.For):
            hit = _repo_call_key_tag(node.iter)
            if hit:
                _, tag = hit
                if tag[0] == "list" and isinstance(node.target, ast.Name):
                    var_types[node.target.id] = ("entity", tag[1])

    # pass 2: constructor kwargs + attribute accesses
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fields = entity_fields.get(node.func.id)
            if fields:
                bad = sorted(
                    kw.arg for kw in node.keywords
                    if kw.arg and kw.arg not in fields
                )
                if bad:
                    violations.append(
                        "%s() got unknown field(s) %s (declared: %s)"
                        % (
                            node.func.id,
                            ", ".join(bad),
                            ", ".join(sorted(fields)),
                        )
                    )
                if len(node.args) > len(fields):
                    violations.append(
                        "%s() called with %d positional args; the model "
                        "declares %d field(s)"
                        % (node.func.id, len(node.args), len(fields))
                    )
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            tag = var_types.get(node.value.id)
            if not tag or node.attr in _DICT_METHODS:
                continue
            if tag[0] == "entity":
                if node.attr not in entity_fields.get(tag[1], set()):
                    violations.append(
                        "%s.%s: unknown field %r on %s (declared: %s)"
                        % (
                            node.value.id,
                            node.attr,
                            node.attr,
                            tag[1],
                            ", ".join(
                                sorted(entity_fields.get(tag[1], set()))
                            ),
                        )
                    )
            elif tag[0] == "dict":
                violations.append(
                    "%s is a dict (designed repository return); use "
                    "['%s'] instead of .%s"
                    % (node.value.id, node.attr, node.attr)
                )
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):

            def _side_kind(n):
                if isinstance(n, ast.Name):
                    # Designed range params (start_*/end_*, floored onto date
                    # columns by _apply_filter_floors) must never be string-
                    # mangled regardless of their declared type.
                    if n.id.startswith(("start_", "end_")):
                        return "date"
                    t = param_types.get(n.id, "")
                    return "date" if "date" in t else None
                if isinstance(n, ast.Constant) and isinstance(n.value, str):
                    return "str"
                return None

            kinds = {_side_kind(node.left), _side_kind(node.right)}
            if kinds == {"date", "str"}:
                violations.append(
                    "date + str concatenation (%s + %s) raises TypeError; "
                    "build the filter values with explicit formatting "
                    "instead"
                    % (
                        ast.unparse(node.left)[:40],
                        ast.unparse(node.right)[:40],
                    )
                )
        elif (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys = var_keys.get(node.value.id)
            if keys and node.slice.value not in keys:
                violations.append(
                    "%s['%s']: unknown dict key %r (returned keys: %s)"
                    % (
                        node.value.id,
                        node.slice.value,
                        node.slice.value,
                        ", ".join(sorted(keys)),
                    )
                )
    return violations


def _service_fill_violations(filled, repo_interface, svc_design, type_ctx=None):
    """Mechanical contract check of an LLM service fill.

    Returns a list of human-readable violations (empty list = accept):
    (1) dropped designed methods, (2) calls to repo attributes/methods that
    are not part of the deterministic repo interface, (3) arity mismatches
    against the declared repo signatures.
    """
    if not filled:
        return ["empty output"]
    try:
        tree = ast.parse(filled)
    except SyntaxError:
        return ["output does not compile"]
    violations = []
    defined = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    required = {
        m.get("name") for m in svc_design.get("methods") or []
        if isinstance(m, dict) and m.get("name")
    }
    missing = required - defined
    if missing:
        violations.append(
            "dropped designed method(s): %s" % ", ".join(sorted(missing))
        )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute):
            continue
        value = func.value
        if not (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == "self"
        ):
            continue
        sig = repo_interface.get(value.attr)
        if sig is None:
            violations.append(
                "calls unknown repository attribute self.%s" % value.attr
            )
            continue
        if func.attr not in sig:
            violations.append(
                "self.%s has no method %s" % (value.attr, func.attr)
            )
            continue
        entries = sig[func.attr]
        if entries == ["_filters"]:
            # list(**filters): any filter kwargs are fine
            continue
        names = [p[0] if isinstance(p, tuple) else p for p in entries]
        req_names = [
            p[0] if isinstance(p, tuple) else p
            for p in entries
            if not (isinstance(p, tuple) and not p[1])
        ]
        n_pos = len(node.args)
        kw_names = {kw.arg for kw in node.keywords if kw.arg}
        if any(kw.arg is None for kw in node.keywords):
            violations.append(
                "self.%s.%s called with **spread — cannot verify arity"
                % (value.attr, func.attr)
            )
            continue
        # Exact-arity contract: every required param must be covered and the
        # call may not pass more args than the method accepts. A call with
        # FEWER args than required params is a guaranteed TypeError at
        # runtime (the 4B model has been caught emitting those).
        provided = n_pos + len(kw_names)
        if provided < len(req_names) or provided > len(names):
            violations.append(
                "self.%s.%s expects params (%s); call provides %d argument(s)"
                % (value.attr, func.attr, ", ".join(names), provided)
            )
        elif not kw_names.issubset(set(names[n_pos:])):
            violations.append(
                "self.%s.%s: keyword(s) %s do not match the trailing params"
                % (
                    value.attr,
                    func.attr,
                    sorted(kw_names - set(names[n_pos:])),
                )
            )
    if type_ctx:
        violations.extend(_semantic_fill_violations(tree, type_ctx))
    return violations


def _service_header_lines(svc_class, entities, entities_by_class,
                          exception_names):
    """Imports + class shell + repo wiring shared by the deterministic
    service and the stub-only mini-skeleton sent to the LLM fill."""
    exception_names = exception_names or []
    repo_attrs = [(_snake(ent) + "_repo", _camel(ent) + "Repository") for ent in entities]
    repo_class_names = sorted({cls for _, cls in repo_attrs})
    lines = [
        '"""Service layer."""',
        "from __future__ import annotations",
        "",
        "import csv",
        "from typing import Any, Dict, List, Optional",
    ]
    # The deterministic create_<entity> recipe stamps date/datetime fields
    # DECLARED auto:"now" with datetime.datetime.now(); import datetime when
    # needed (same predicate as the recipe — never an unused import).
    if any(
        f.get("auto") == "now"
        and f.get("name") != "id"
        and f.get("type") in ("date", "datetime")
        for ent in entities_by_class.values()
        for f in (ent.get("fields") or [])
        if isinstance(f, dict)
    ):
        lines.append("import datetime")
    lines += [
        "",
        "from database import Database",
        "from models import %s" % ", ".join(entities),
    ]
    for rcls in repo_class_names:
        lines.append("from %s import %s" % (_snake(rcls), rcls))
    if exception_names:
        lines.append("from exceptions import %s" % ", ".join(sorted(exception_names)))
    lines += [
        "",
        "",
        "class %s:" % svc_class,
        "    def __init__(self, db: Database) -> None:",
        "        self.db = db",
    ]
    for attr, cls in repo_attrs:
        lines.append("        self.%s = %s(db)" % (attr, cls))
    lines.append("")
    return lines


def _indent_block(src, spaces):
    pad = " " * spaces
    return "\n".join(pad + ln if ln.strip() else ln for ln in src.split("\n"))


def _splice_functions(text, replacements):
    """Apply (start_line, end_line, new_src) replacements (1-based, inclusive)
    bottom-up so earlier offsets stay valid."""
    lines = text.split("\n")
    for start, end, new_src in sorted(replacements, reverse=True):
        lines[start - 1 : end] = new_src.split("\n")
    return "\n".join(lines)


def _merge_stub_bodies(deterministic, filled, stub_names):
    """Splice the implementations of `stub_names` from `filled` into
    `deterministic`, leaving every other byte of the deterministic file
    untouched. Returns the merged text, or None when the fill does not
    provide exactly the expected methods."""
    try:
        ftree = ast.parse(filled)
        dtree = ast.parse(deterministic)
    except SyntaxError:
        return None
    needed = set(stub_names)
    found = {}
    for node in ast.walk(ftree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in needed
        ):
            found[node.name] = node
    if set(found) != needed:
        return None
    repls = []
    for node in ast.walk(dtree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in needed
        ):
            new_src = ast.unparse(found[node.name])
            repls.append(
                (
                    node.lineno,
                    node.end_lineno,
                    _indent_block(new_src, node.col_offset),
                )
            )
    if len(repls) != len(needed):
        return None
    return _splice_functions(deterministic, repls)


def _repo_dict_keys(repo_sources, entities_by_class, designs):
    """{(repo_attr, method): set(string keys)} actually returned by
    Dict-returning DESIGNED repository customs, extracted from the
    RENDERED repository sources (deterministic bodies + accepted fills).
    Lets a service fill be validated against REAL dictionary keys instead
    of hallucinated ones."""
    repo_designs = {}
    for path, kind, data in designs or []:
        if kind == "repositories" and isinstance(data, dict):
            repo_designs[Path(path).stem] = data

    out = {}
    for ent in entities_by_class.values():
        attr = _snake(ent["name"]) + "_repo"
        rdes = repo_designs.get(_snake(ent["name"]) + "_repository")
        src = repo_sources.get(_snake(ent["name"]) + "_repository.py")
        if not rdes or not src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        fdefs = {
            n.name: n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for m in rdes.get("methods") or []:
            if not isinstance(m, dict) or not m.get("name"):
                continue
            ret = (m.get("returns") or "").lower()
            if "dict" not in ret:
                continue
            fn = fdefs.get(m["name"])
            if fn is None:
                continue
            keys = set()
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Return)
                    and isinstance(node.value, ast.Dict)
                ):
                    for k in node.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keys.add(k.value)
            if keys:
                out[(attr, m["name"])] = keys
    return out


def _render_service_file(svc_design, svc_class, designs, entities_by_class,
                         prompt_text, exception_names=None, verbose=False,
                         repo_sources=None):
    """Deterministic service: real contract bodies + stubs for extras.

    Contract methods (the tested surface) get real bodies rendered here with
    zero LLM involvement. Extras the LLM designed are rendered as
    NotImplementedError stubs; when `prompt_text` is given, ONLY the stub
    methods travel to the LLM inside a mini-skeleton, and an accepted fill is
    spliced back per-method — deterministic bodies can never be degraded by
    the fill.
    """
    exception_names = exception_names or []
    entities = sorted(entities_by_class)

    lines = _service_header_lines(
        svc_class, entities, entities_by_class, exception_names
    )

    repo_customs = _zero_param_dict_repo_customs(designs, entities_by_class)
    for m in svc_design.get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        body = _service_method_body(
            m, entities_by_class, exception_names, repo_customs
        )
        if body is not None:
            def_line = _method_stub_code(m, 1).split("\n")[0]
            lines.append(def_line)
            lines.extend(body)
            lines.append("")
            continue
        lines.append(_method_stub_code(m, 1))
        lines.append("")

    deterministic = "\n".join(lines).rstrip() + "\n"
    # Only involve the LLM when there are non-contract method bodies left to
    # fill. If every designed method has a deterministic body, hand back the
    # deterministic service untouched — no hallucination surface at all.
    stubs = [
        m for m in svc_design.get("methods") or []
        if isinstance(m, dict) and m.get("name")
        and _service_method_body(
            m, entities_by_class, exception_names, repo_customs
        ) is None
    ]
    if not prompt_text or not stubs:
        return deterministic
    # Tell the fill which repo methods exist (it may only call these on
    # self.*_repo). Validation is scoped to the STUB methods only: the
    # deterministic contract bodies are not part of the fill context.
    repo_interface = _service_repo_interface(entities_by_class, designs)
    type_ctx = _service_type_context(entities_by_class, designs)
    if repo_sources:
        type_ctx["dict_keys"] = _repo_dict_keys(
            repo_sources, entities_by_class, designs
        )
    hint_parts = [
        "AVAILABLE REPOSITORY METHODS — you may call ONLY these on self.*_repo "
        "(never invent repository methods):"
    ]
    if repo_interface:
        for attr in sorted(repo_interface):
            names = [
                p[0] if isinstance(p, tuple) else p
                for p in repo_interface[attr]
            ]
            hint_parts.append(
                "  self.%s: %s" % (attr, ", ".join(sorted(names)))
            )
    else:
        hint_parts.append("  (none)")
    fill_hint = "\n".join(hint_parts)
    fill_hint += (
        "\n\nMODEL FIELD NAMES — constructor keyword arguments and "
        "attribute access MUST use exactly these:\n"
        + "\n".join(
            "  %s(%s)"
            % (cls, ", ".join(sorted(type_ctx["entity_fields"][cls])))
            for cls in sorted(type_ctx["entity_fields"])
        )
    )
    dict_key_lines = [
        "  self.%s.%s(...) -> dict with keys: %s"
        % (attr, meth, ", ".join(sorted(keys)))
        for (attr, meth), keys in sorted(type_ctx.get("dict_keys", {}).items())
    ]
    if dict_key_lines:
        fill_hint += (
            "\n\nDICT RETURN KEYS — when a call below returns a dict, index "
            "it ONLY with these keys:\n" + "\n".join(dict_key_lines)
        )

    # Mini-skeleton: header + ONLY the stub methods. The model never sees the
    # deterministic bodies, so it cannot rewrite/degrade them; its output is
    # spliced back into the deterministic file per-method.
    stub_design = {"methods": stubs}
    stub_names = [m["name"] for m in stubs]
    mini = "\n".join(
        _service_header_lines(
            svc_class, entities, entities_by_class, exception_names
        )
        + [_method_stub_code(m, 1) for m in stubs]
    ).rstrip() + "\n"

    def _accept(candidate):
        """Validate a mini-skeleton fill and splice it into the deterministic
        service. Returns the merged text or None."""
        if not candidate:
            return None
        if _service_fill_violations(
            candidate, repo_interface, stub_design, type_ctx
        ):
            return None
        return _merge_stub_bodies(deterministic, candidate, stub_names)

    filled = _llm_fill("service", fill_hint, mini, prompt_text, verbose=verbose)
    merged = _accept(filled)
    if merged is not None:
        return merged
    if filled and verbose:
        print(
            "    [fill] service: rejected (%s)"
            % "; ".join(
                _service_fill_violations(
                    filled, repo_interface, stub_design, type_ctx
                )[:3]
            )
        )
    # One corrective retry: show the model EXACTLY which calls violated
    # the repository contract so it fixes those without touching anything.
    violations = (
        _service_fill_violations(filled, repo_interface, stub_design, type_ctx)
        if filled else ["empty output"]
    )
    corrective = (
        fill_hint
        + "\n\nYOUR PREVIOUS OUTPUT WAS REJECTED FOR THESE CONTRACT "
        + "VIOLATIONS (fix ONLY these, keep everything else identical):\n"
        + "\n".join("  - " + v for v in violations[:8])
    )
    refilled = _llm_fill(
        "service", corrective, mini, prompt_text, verbose=verbose
    )
    merged = _accept(refilled)
    if merged is not None:
        return merged
    return deterministic


def _render_cli_file(design, svc_class, entities_by_class, service_methods,
                     verbose=False, db_path="app.db"):
    """Deterministic click CLI: one flat top-level command per command.

    A designed command `group=["item"], name="add"` becomes
    a flat `@click.command()` named `<group>_<name>` registered on the root
    `cli` group, wired to the designed service method with option->param
    mapping. No LLM involvement.
    """
    commands = design.get("commands") or []
    svc_snake = _snake(svc_class)
    seen_flat = set()

    lines = [
        "import click",
        "from database import Database",
        "from %s import %s" % (svc_snake, svc_class),
        "",
        'DB_PATH = "%s"' % db_path,
        "",
        "@click.group()",
        "def cli():",
        '    """Application root."""',
        "",
    ]

    for c in commands:
        if not isinstance(c, dict):
            continue
        group = c.get("group") or []
        name = c.get("name")
        if not name:
            continue
        # click registers commands under their function-name; hyphenate and give
        # the function an identifier-safe name (underscores) while click
        # exposes the hyphenated alias via the explicit @cli.command(name=...).
        # A doubled verb (["expense", "add"] + "add") collapses to the parent
        # path so the flat command is "expense-add", never "add-add"; any
        # residual collision gets a numeric suffix instead of being silently
        # overwritten by a later @cli.command registration.
        while group and group[-1] == name:
            group = group[:-1]
        leaf = group[-1] if group else ""
        flat_hyphen = "-".join([leaf, name]) if leaf else name
        if flat_hyphen in seen_flat and len(group) >= 2:
            flat_hyphen = "-".join(group + [name])
        base = flat_hyphen
        k = 2
        while flat_hyphen in seen_flat:
            flat_hyphen = "%s-%d" % (base, k)
            k += 1
        seen_flat.add(flat_hyphen)
        flat_ident = flat_hyphen.replace("-", "_")
        opts = c.get("options") or []
        target = c.get("target") or name or ""

        lines.append("@cli.command(%r)" % flat_hyphen)
        for o in opts:
            oname = o.get("name")
            if not oname:
                continue
            otype = o.get("type") or "str"
            req = "required=True" if o.get("required") else ""
            if otype == "int":
                lines.append("@click.option(%r, type=int%s)"
                             % (oname, (", " + req) if req else ""))
            elif otype == "flag":
                lines.append("@click.option(%r, is_flag=True, default=False)" % oname)
            else:
                lines.append("@click.option(%r%s)"
                             % (oname, (", " + req) if req else ""))
        pvars = ", ".join(_optvar(o) for o in opts if o.get("name"))
        lines.append("def %s(%s):" % (flat_ident, pvars))
        lines.append('    """%s"""' % "/".join(group + [name]))
        call = _build_service_call(target, opts, service_methods)
        # The service __init__ takes a Database object, not a path string.
        lines.append("    svc = %s(Database(DB_PATH))" % svc_class)
        lines.append("    " + call)
        lines.append("")

    lines.append("")
    lines.append('if __name__ == "__main__":')
    lines.append("    cli()")
    return "\n".join(lines).rstrip() + "\n"


def _optvar(o):
    return re.sub(r"[- ]", "_", (o.get("name") or "").lstrip("-"))


def _match_param(key, params):
    """Exact match first, then bounded suffix matching (--category ->
    category_id, --price -> price_cents)."""
    if key in params:
        return key
    return next(
        (
            p
            for p in params
            if p.startswith(key + "_") or p.endswith("_" + key)
        ),
        None,
    )


def _build_service_call(target, opts, service_methods):
    """Wire click options to a service method call, passing ONLY options
    that map to real parameters of the target's designed signature."""
    sig = {}
    for m in service_methods or []:
        if isinstance(m, dict) and m.get("name"):
            sig[m["name"]] = [
                p.get("name")
                for p in (m.get("params") or [])
                if isinstance(p, dict) and p.get("name")
            ]
    params = sig.get(target)

    def key_of(o):
        return o.get("field") or _optvar(o)

    if params and "data" in params:
        # update-style (id, data) target: map direct params, pack every
        # other option into the data dict instead of dropping them
        parts, packed, used = [], [], set()
        for p in params:
            if p == "data":
                continue
            for o in opts:
                if o.get("name") and key_of(o) == p:
                    parts.append("%s=%s" % (p, _optvar(o)))
                    used.add(key_of(o))
                    break
        for o in opts:
            if not o.get("name"):
                continue
            k = key_of(o)
            if k in used or k in params:
                continue
            used.add(k)
            packed.append("'%s': %s" % (k, _optvar(o)))
        if packed:
            parts.append("data={%s}" % ", ".join(packed))
        return "result = svc.%s(%s)" % (target, ", ".join(parts))

    kwargs, used = [], set()
    for o in opts:
        if not o.get("name"):
            continue
        key = key_of(o)
        if key in used:
            continue
        match = _match_param(key, params) if params is not None else key
        if match is None:
            continue  # option does not map to the target signature
        used.add(key)
        kwargs.append("%s=%s" % (match, _optvar(o)))
    return "result = svc.%s(%s)" % (target, ", ".join(kwargs))

def _generate_file(file_spec, manifest, prompt_text, prior_files,
                   verbose=False, db_file="app.db"):
    file_name = file_spec["file"]
    file_role = file_spec.get("role", "")
    imports_from = file_spec.get("imports_from", [])

    dep_lines = []
    for dep_name in imports_from:
        for spec in manifest:
            if Path(spec["file"]).stem == dep_name and dep_name in prior_files:
                exports = _extract_defined_names(prior_files[dep_name])
                if exports:
                    dep_lines.append(
                        "  %s.py exports: %s" % (dep_name, ", ".join(sorted(exports)))
                    )
    dep_context = "\n".join(dep_lines) if dep_lines else "  (none)"

    all_stems = {Path(s["file"]).stem: s["file"] for s in manifest}
    allowed = [s for s in imports_from if s in all_stems]
    import_map = "\n".join(
        '  from %s import <Name>  (from "%s")' % (stem, all_stems[stem])
        for stem in allowed
    ) if allowed else "  (none)"

    file_prompt = dedent("""\
        Generate file `%s`. Role: %s
        SIBLING MODULES (import from these):
        %s
        ALLOWED IMPORTS:
        %s
        RULES:
        - Use the exact class/method names, argument order, and argument
          types from the project design (never invent new ones).
        - Import ONLY the names listed above.
        - Do NOT invent module or function names.
        - Use stdlib sqlite3. No sqlalchemy.
        - The SQLite database filename is "%s" — use exactly this
          name wherever the project opens its database.
        - IDs are Optional[int] (default None).
        - Return ONLY raw Python source code.
    """) % (file_name, file_role, dep_context, import_map, db_file)

    sibling_exports = {}
    for name, content in prior_files.items():
        sibling_exports[Path(name).stem] = _extract_defined_names(content)

    code = generate_with_validation(
        file_prompt, prompt_text,
        sibling_exports=sibling_exports,
        verbose=verbose, max_retries=3,
    )
    return code, "ok" if code else "generation returned None"


def _manifest_first_blocks(prompt_text, verbose=False):
    """smith-style manifest-first pipeline.

    Design everything as schema-constrained JSON, render all mechanical files
    deterministically, and let the LLM fill only business bodies (service and
    repository custom methods) inside locked skeletons. Returns {file: code}.
    """
    if verbose:
        print("    Generating architecture manifest...")
    layout = _generate_manifest(prompt_text, verbose=verbose)
    if not layout:
        if verbose:
            print("    Manifest failed; generation aborted (no fallback)")
        return None, None
    manifest, db_file = _validate_manifest(layout)

    designs = []  # (path, kind, data)
    entities_by_class = {}

    if verbose:
        print("    Design phase (schema-constrained JSON)...")

    def _design_into(path, kind, context):
        """One schema-constrained design call, appended to `designs`."""
        data = _design_module(path, kind, prompt_text, context, verbose)
        if data is None:
            print("    [design] %s: FAILED" % path, file=sys.stderr)
            return None
        designs.append((path, kind, data))
        if verbose:
            print("      - %s [%s] %s" % (path, kind, _describe_design(kind, data)))
        return data

    # 1. exceptions — ALWAYS designed from the spec under the schema; the
    # prompt text is never regex-scanned. The canonical module survives only
    # when the design names exceptions or the layout declared the file.
    declared_exc = [
        s["file"] for s in manifest
        if s["kind"] == "exceptions" or "exception" in Path(s["file"]).stem
    ]
    exception_names = []
    for ep in (declared_exc or ["exceptions.py"]):
        data = _design_into(ep, "exceptions", "(none)")
        if data is None:
            return None, None
        for e in data.get("exceptions") or []:
            if e not in exception_names:
                exception_names.append(e)
    if not declared_exc and not exception_names:
        # Nothing declared and nothing designed: no exceptions module at all.
        designs[:] = [(p, k, d) for p, k, d in designs if k != "exceptions"]

    # 2. models
    model_paths = [s["file"] for s in manifest if s["kind"] == "models"]
    for mp in model_paths:
        data = _design_into(mp, "models", _fmt_design_context(designs))
        if data is None:
            return None, None
        for ent in data.get("entities") or []:
            if isinstance(ent, dict) and ent.get("name"):
                entities_by_class[ent["name"]] = ent

    if not entities_by_class:
        print("    [design] no entities designed", file=sys.stderr)
        return None, None

    # 2.5 Generic repository/service stems are renamed to per-entity files
    # using the DECLARED entity metadata of the layout design (falling back
    # to the first designed entity) — no regex sniffing of the spec text.
    first_entity = _snake(sorted(entities_by_class)[0])
    for spec in manifest:
        stem = Path(spec["file"]).stem
        if stem not in ("repository", "repositories", "service", "services"):
            continue
        kind_word = "repository" if "repositor" in stem else "service"
        target = "%s_%s.py" % (spec.get("entity") or first_entity, kind_word)
        if spec["file"] == target:
            continue
        old_stem = stem
        spec["file"] = target
        for s in manifest:
            s["imports_from"] = [
                (target[:-3] if Path(f).stem == old_stem else f)
                for f in s.get("imports_from", [])
            ]

    # 3. repositories (custom methods only; CRUD is generated)
    repo_paths = [s["file"] for s in manifest if s["kind"] == "repository"]
    for rp in repo_paths:
        if _design_into(rp, "repositories", _fmt_design_context(designs)) is None:
            return None, None

    # 4. services
    svc_paths = [s["file"] for s in manifest if s["kind"] == "service"]
    for sp in svc_paths:
        if _design_into(sp, "services", _fmt_design_context(designs)) is None:
            return None, None

    # 5. CLI (targets constrained to designed service methods).
    # A CLI design failure is NOT fatal: the deterministic repos/service are
    # still valid, so keep them and generate cli.py via the per-file path
    # later (legacy _generate_file) rather than abandoning the whole
    # manifest-first pipeline to the volatile legacy multi-pass.
    cli_paths = [s["file"] for s in manifest if s["kind"] == "cli"]
    svc_design = next((d for p, k, d in designs if k == "services"), None)
    service_methods = (svc_design or {}).get("methods") or []
    cli_failed = False
    for cp in cli_paths:
        data = _design_cli(prompt_text, _fmt_design_context(designs), service_methods, verbose)
        if data is None:
            print("    [design] %s: FAILED (will generate via per-file path)" % cp, file=sys.stderr)
            cli_failed = True
            continue
        designs.append((cp, "cli", data))
        if verbose:
            print("      - %s [cli] commands=%d"
                  % (cp, len(data.get("commands") or [])))

    # Deterministic floor for list_filters: cover the parameters the
    # designed service/repository signatures actually use. Declarations
    # from the models design always win (see _apply_filter_floors).
    _apply_filter_floors(entities_by_class, designs)
    # Deterministic floor for service impls on unambiguous aggregate
    # shapes (Dict-returning methods over a single date+numeric entity).
    _apply_impl_floors(entities_by_class, designs)

    # Exception names come ONLY from the schema-constrained exceptions
    # design (collected in step 1) — there is no spec-text floor anymore.

    # service_methods = the designed service methods (CLI targets must map
    # to them, so this is computed once here)
    svc_design = next((d for p, k, d in designs if k == "services"), None)
    service_methods = (svc_design or {}).get("methods") or []

    # Design context for structural validation — replaces every form of
    # spec-text sniffing: what MUST exist in the final tree is exactly what
    # the schema-constrained designs declared, nothing else.
    design_ctx = {
        "exceptions": list(exception_names),
        "entities": {
            cls: [
                f.get("name") for f in (ent.get("fields") or []) if f.get("name")
            ]
            for cls, ent in entities_by_class.items()
        },
        "service_file": svc_paths[0] if svc_paths else None,
        "service_methods": [
            m.get("name") for m in service_methods
            if isinstance(m, dict) and m.get("name")
        ],
        "db_file": db_file,
    }

    # ---- Render phase (deterministic) ----
    files = {}
    svc_class = "App"
    if svc_paths:
        stem = Path(svc_paths[0]).stem
        if stem.endswith("_service"):
            stem = stem[: -len("_service")]
        svc_class = _camel(stem) + "Service"
    for path, kind, data in designs:
        if kind == "exceptions":
            files[path] = _render_exceptions_file(data)
        elif kind == "models":
            files[path] = _render_models_file(data)
        elif kind == "cli":
            files[path] = _render_cli_file(
                data, svc_class, entities_by_class, service_methods,
                verbose, db_path=db_file,
            )

    # ---- Fill phase (LLM, locked skeletons; deterministic contract bodies) ----
    if verbose:
        print("    Fill phase (service + repository custom methods)...")

    # 5.1 repository files: deterministic CRUD + stubs; UNIQUE-pair custom
    # methods (get_by_<a>_and_<b>) are rendered deterministically from the
    # designed unique_together by _render_repository_file.
    for rp in repo_paths:
        stem = Path(rp).stem
        ent_snake = stem[: -len("_repository")] if stem.endswith("_repository") else stem
        repo_design = next((d for p, k, d in designs if p == rp), {})
        files[rp] = _render_repository_file(
            ent_snake, repo_design, entities_by_class, exception_names,
            prompt_text=prompt_text, verbose=verbose,
        )

    # 5.2 service file: deterministic contract bodies; LLM fills only extras
    for sp in svc_paths:
        svc_design = next((d for p, k, d in designs if p == sp), {})
        body = _render_service_file(
            svc_design, svc_class, designs, entities_by_class,
            prompt_text, exception_names, verbose,
            repo_sources={p: files[p] for p in repo_paths},
        )
        files[sp] = body

    # 5.3 CLI fallback: when the CLI design failed, keep the deterministic
    # pipeline and generate cli.py via the per-file path instead of
    # abandoning everything to the volatile legacy multi-pass.
    if cli_failed:
        for spec in manifest:
            if Path(spec["file"]).stem == "cli" and spec["file"] not in files:
                if verbose:
                    print("    Generating %s via per-file path (CLI design failed)..." % spec["file"])
                content, status = _generate_file(
                    spec, manifest, prompt_text, files,
                    verbose=verbose, db_file=db_file,
                )
                if content:
                    files[spec["file"]] = content
                else:
                    print("    %s: %s" % (spec["file"], status), file=sys.stderr)

    # Provisional database.py: repos/service import `from database import
    # Database`, but database.py is normally generated later (Phase 4) from
    # the final models. Synthesize it now from the rendered models so this
    # validation pass resolves the sibling import; the outer flow regenerates
    # it from the written models afterward.
    if "database.py" not in files and "models.py" in files:
        model_classes = _extract_model_ast({"models.py": files["models.py"]})
        if model_classes:
            files["database.py"] = _generate_database_file(model_classes, db_file)

    # ensure every manifest file exists (e.g. a main.py the LLM invented)
    for spec in manifest:
        fn = spec["file"]
        if fn not in files:
            files[fn] = ""

    # Mechanical AST validation of the generated tree (same as the legacy
    # path): syntax, sibling-import resolution, structural checks.
    all_exports = {Path(f).stem: _extract_defined_names(c) for f, c in files.items()}
    ast_errors, ast_fixes = _check_syntax_and_imports(files, all_exports)
    for fp, fixed in ast_fixes.items():
        files[fp] = fixed
    struct_errors = _check_structural(files, design_ctx)
    if verbose and (ast_errors or struct_errors):
        print("    Validation: %d issue(s)" % (len(ast_errors) + len(struct_errors)))
        for e in (ast_errors + struct_errors)[:5]:
            print("      - %s" % e)

    return files, design_ctx


# ---------------------------------------------------------------------------
# Manifest-first entry point (used by process_prompt for multi-file specs)
# ---------------------------------------------------------------------------

def _multi_pass(prompt_text, verbose=False):
    """Manifest-first generation with a deterministic finalize phase.

    1. _manifest_first_blocks: schema-constrained design -> deterministic
       render -> LLM-fill of only non-contract bodies.
    2. Finalize (zero-LLM-cost where possible): AST import validation,
       structural validation, targeted LLM repair with error accumulation
       (contracts.md accumulate_errors pattern), then a deterministic
       database.py generated from the final model AST.

    Strict pipeline: there is no fallback. If the manifest-first generation
    fails, we raise so the prompt is reported as failed instead of silently
    degrading to the removed legacy multi-pass / single-pass paths (which
    let the 4B model write full file bodies and hallucinate).
    """
    files, design_ctx = _manifest_first_blocks(prompt_text, verbose=verbose)
    if not files:
        raise RuntimeError(
            "manifest-first pipeline failed for this prompt "
            "(legacy fallback paths have been removed)"
        )

    # ---- Phase 4 (early): deterministic database.py from the model AST ----
    # Generate BEFORE validation so `from database import Database` resolves
    # and the table-structure check passes. Prevents the LLM repair loop from
    # firing on a clean deterministic output (the 4B model would rewrite good
    # files and reintroduce hallucinated code).
    model_classes = _extract_model_ast(files)
    if model_classes:
        files["database.py"] = _generate_database_file(
            model_classes, design_ctx.get("db_file", "app.db")
        )
        if verbose:
            print("    Generated database.py from model AST (%d tables)"
                  % len(model_classes))

    # ---- Finalize phase (deterministic AST checks) ----
    all_exports = {Path(f).stem: _extract_defined_names(c) for f, c in files.items()}
    ast_errors, ast_fixes = _check_syntax_and_imports(files, all_exports)
    for fp, fixed in ast_fixes.items():
        files[fp] = fixed

    struct_errors = _check_structural(files, design_ctx)
    all_errors = ast_errors + struct_errors
    if all_errors and verbose:
        print("    Validation: %d issue(s)" % len(all_errors))
        for err in all_errors[:5]:
            print("      - %s" % err)

    # ---- LLM repair with per-file error accumulation (targeted) ----
    repair_history = {}
    for repair_attempt in range(3):
        if not all_errors:
            break
        files_to_fix = {}
        for err in all_errors:
            for fp in files:
                if fp in err:
                    files_to_fix.setdefault(fp, []).append(err)
        if not files_to_fix:
            break
        if verbose:
            print("    Repair %d: %s"
                  % (repair_attempt + 1, ", ".join(sorted(files_to_fix))))

        for fp, errs in files_to_fix.items():
            file_content = files[fp]
            seen = set(repair_history.get(fp, []))
            for e in errs:
                if e not in seen:
                    repair_history.setdefault(fp, []).append(e)
                    seen.add(e)
            err_list = repair_history[fp][-6:]
            repair_prompt = dedent("""\
                Fix errors in this Python file.

                ERRORS (from all failed attempts — do NOT reintroduce any):
                %s

                FILE (%s):
                %s
                Return ONLY the corrected raw Python source code.
            """) % (
                "\n".join("  - %s" % e for e in err_list),
                fp,
                file_content[:3000],
            )
            raw = generate_code(repair_prompt)
            repaired = _extract_code_block(raw)
            if repaired and len(repaired) > len(file_content) * 0.3:
                files[fp] = repaired
                if verbose:
                    print("      Repaired %s" % fp)

        all_exports = {Path(f).stem: _extract_defined_names(c) for f, c in files.items()}
        ast_errors, ast_fixes = _check_syntax_and_imports(files, all_exports)
        for fp, fixed in ast_fixes.items():
            files[fp] = fixed
        struct_errors = _check_structural(files, design_ctx)
        all_errors = ast_errors + struct_errors
        if verbose and all_errors:
            print("    After repair: %d remaining" % len(all_errors))

    # ---- Phase 4: deterministic database.py from the final model AST ----
    model_classes = _extract_model_ast(files)
    if model_classes:
        files["database.py"] = _generate_database_file(
            model_classes, design_ctx.get("db_file", "app.db")
        )
        if verbose:
            print("    Generated database.py from model AST (%d tables)"
                  % len(model_classes))

    return files


# ---------------------------------------------------------------------------
# Single-pass generation
# ---------------------------------------------------------------------------

def _single_pass(prompt_text, verbose=False):
    full_prompt = dedent("""\
        %s
        Return ONLY raw Python source code -- no markdown, no commentary.
        For multi-file projects: # === file: path/to/file.py ===
    """) % prompt_text

    code = generate_with_validation(
        full_prompt, prompt_text,
        verbose=verbose, max_retries=3,
    )
    return _split_multifile(code or "")


# ---------------------------------------------------------------------------
# Fix relative imports
# ---------------------------------------------------------------------------

def _fix_relative_imports(files, verbose=False):
    fixed = {}
    for filepath, content in files.items():
        new_content = re.sub(r"from \.(\w+)", r"from \1", content)
        if new_content != content and verbose:
            print("    Fixed relative imports in %s" % filepath)
        fixed[filepath] = new_content
    return fixed


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def process_prompt(prompt_name, prompt_path, verbose=True):
    if verbose:
        print("\n" + "=" * 60)
        print("  Prompt : %s" % prompt_name)
        print("  Source : %s" % prompt_path)
        print("=" * 60)

    prompt_text = read_prompt(prompt_path)
    if verbose:
        print("\n--- Prompt ---\n%s\n--------------\n" % prompt_text)
        print("Generating code ...")

    mode = _route_mode(prompt_text, verbose=verbose)
    if verbose:
        print("  Mode: %s-pass" % mode)
    if mode == "multi":
        files = _multi_pass(prompt_text, verbose=verbose)
    else:
        files = _single_pass(prompt_text, verbose=verbose)

    if len(files) > 1:
        files = _fix_relative_imports(files, verbose=verbose)

    project_dir = OUTPUT_DIR / _output_name_for_prompt(prompt_name)
    project_dir.mkdir(parents=True, exist_ok=True)

    for rel_path, content in files.items():
        target = project_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + "\n", encoding="utf-8")
        if verbose:
            print("  wrote %s" % target.relative_to(Path.cwd()))

    # Run ruff --fix for style cleanup
    if len(files) > 1:
        _run_ruff_fix(project_dir)

    if verbose:
        print("\n  Project written to %s/\n" % project_dir.relative_to(Path.cwd()))
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Neurosymbolic Python Coding Agent")
    parser.add_argument("--prompt", "-p", help="Process a single prompt by name.")
    parser.add_argument("--list", "-l", action="store_true", help="List available prompts.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress verbose output.")
    args = parser.parse_args()

    prompts = discover_prompts()
    if not prompts:
        print("No prompts found in prompts/", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print("Available prompts:")
        for name, path in prompts.items():
            print("  %-25s (%s)" % (name, path.name))
        sys.exit(0)

    if args.prompt:
        key = _normalise_prompt_name(args.prompt)
        matches = [k for k in prompts if key in k]
        if not matches:
            print("No prompt matching '%s'. Available: %s" % (args.prompt, ", ".join(prompts)), file=sys.stderr)
            sys.exit(1)
        targets = {m: prompts[m] for m in matches}
    else:
        targets = prompts

    verbose = not args.quiet
    succeeded, failed = 0, 0

    for name, path in targets.items():
        try:
            if process_prompt(name, path, verbose=verbose):
                succeeded += 1
        except Exception as exc:
            print("  FAILED: %s" % exc, file=sys.stderr)
            failed += 1

    print("\nDone -- %d succeeded, %d failed out of %d prompt(s)." % (succeeded, failed, len(targets)))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
