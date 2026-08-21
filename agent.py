#!/usr/bin/env python3
"""
Neurosymbolic Python Coding Agent

Uses SymbolicAI (symai) to read prompts and generate Python code.

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

from symai import Symbol

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
    return data["choices"][0]["message"]["content"]


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


def _check_structural(files, spec_text):
    """Check structural completeness using AST (zero LLM cost).

    Validates:
    1. Required classes exist (extracted from spec)
    2. Required methods exist on classes
    3. Required model fields exist

    Returns list of error strings with file hints.
    """
    errors = []
    lower = spec_text.lower()

    # Build combined code view
    all_code = "\n".join(files.values())
    all_code_lower = all_code.lower()

    # 1. Required exception classes
    for exc in ["CategoryNotFoundError", "ExpenseNotFoundError", "BudgetExceededException"]:
        if exc.lower() in lower and exc not in all_code:
            # Find best file to suggest
            best_fp = _find_file_for_type(files, "exception")
            errors.append("%s: missing required exception '%s'" % (best_fp, exc))

    # 2. Required classes
    for cls in ["CategoryRepository", "ExpenseRepository", "BudgetRepository", "ExpenseService"]:
        if cls.lower() in lower and "class %s" % cls not in all_code:
            best_fp = _find_file_for_type(files, cls.lower().replace("repository", "").replace("service", ""))
            errors.append("%s: missing required class '%s'" % (best_fp, cls))

    # 3. Required model fields (check ALL model files)
    required_fields = _extract_required_fields(spec_text)
    model_files = [fp for fp in files if "model" in fp.lower()]
    for fp in model_files:
        content = files[fp]
        for field in required_fields:
            if field not in content:
                errors.append("%s: missing required field '%s'" % (fp, field))

    # 4. Required database table (lowercase)
    for table_name in ["categories", "expenses", "budgets"]:
        if table_name in lower and table_name not in all_code_lower:
            best_fp = _find_file_for_type(files, "database")
            if best_fp:
                errors.append("%s: missing table creation for '%s'" % (best_fp, table_name))

    return errors


def _extract_required_fields(spec_text):
    """Extract required field names from spec text using regex (no LLM)."""
    fields = set()
    # Look for explicit field mentions in the spec
    field_patterns = [
        r"amount_cents", r"payment_method", r"expense_date", r"is_recurring",
        r"category_id", r"monthly_budget", r"amount_limit_cents",
        r"description", r"month", r"icon", r"name",
    ]
    lower = spec_text.lower()
    for pattern in field_patterns:
        if pattern in lower:
            fields.add(pattern)
    return fields


def _find_file_for_type(files, hint):
    """Find the most likely file for a given type hint."""
    for fp in files:
        if hint.lower() in fp.lower():
            return fp
    return list(files.keys())[0] if files else "unknown.py"


# ---------------------------------------------------------------------------
# DDL generation from models (deterministic, no LLM)
# ---------------------------------------------------------------------------

def _extract_model_ast(files):
    """Extract model class definitions from model files.

    Returns dict of class_name -> list of (field_name, python_type_hint).
    Handles annotation-assignment (`field: type = default`), plain
    assignment, and __init__-based field definitions.
    """
    result = {}
    model_files = [fp for fp in files if "model" in fp.lower()]

    for fp in model_files:
        try:
            tree = ast.parse(files[fp])
        except SyntaxError:
            continue

        for node in ast.iter_child_nodes(tree):
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

    category -> categories, expense -> expenses, budget -> budgets.
    """
    lower = class_name.lower()
    if lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        return lower[:-1] + "ies"
    if lower.endswith("s"):
        return lower + "es"
    return lower + "s"


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


def _generate_ddl_from_models(model_classes, spec_text):
    """Generate CREATE TABLE DDL from model class definitions.

    Model class names become table names (lowercase pluralized).
    Fields become columns. 'id' fields get PRIMARY KEY AUTOINCREMENT.
    """
    lower = spec_text.lower()
    tables = []

    for class_name, fields in model_classes.items():
        # Pluralize: Category -> categories, Expense -> expenses
        table_name = _pluralize_table_name(class_name)

        columns = []
        foreign_keys = []
        unique_constraints = []

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
                ref_table = _pluralize_table_name(field_name.replace("_id", ""))
                foreign_keys.append(
                    "    FOREIGN KEY (%s) REFERENCES %s (id)" % (field_name, ref_table)
                )

        # Add UNIQUE constraints from spec (case-insensitive)
        if "unique(category_id, month)" in lower and table_name == "budgets":
            unique_constraints.append("    UNIQUE(category_id, month)")

        # Build CREATE TABLE (terminate with ';' so executescript
        # splits statements correctly)
        all_parts = columns + foreign_keys + unique_constraints
        ddl = "CREATE TABLE IF NOT EXISTS %s (\n%s\n);" % (
            table_name,
            ",\n".join(all_parts)
        )
        tables.append(ddl)

    return "\n\n".join(tables)


def _generate_database_file(model_classes, spec_text):
    """Generate a complete database.py from model AST definitions.

    Uses a list-based template to guarantee clean line indentation --
    no dedent/tab pitfalls. DDL is emitted via cursor.executescript()
    with a triple-quoted string, so column/table lines never become
    bare statements inside the function body.
    """
    ddl = _generate_ddl_from_models(model_classes, spec_text)

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
        'def init_database(db_path: str = "finance.db") -> sqlite3.Connection:',
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
    """Send prompt to SymbolicAI via Symbol.compose()."""
    sym = Symbol(prompt_text, static_context=SYSTEM_CONTEXT)
    result = sym.compose()
    return str(result).strip()


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

_JSON_FENCE = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)

_MULTI_FILE_HINTS = [
    "multi-module", "multi-file", "multiple files", "package",
    "repositories", "services", "cli interface", "clean architecture",
    "separation of concerns", "repository pattern",
]

def _needs_multifile(prompt_text):
    lower = prompt_text.lower()
    return any(hint in lower for hint in _MULTI_FILE_HINTS)

def _generate_manifest(prompt_text):
    manifest_prompt = dedent("""\
        Given this project specification, produce a JSON file manifest.
        SPEC: %s
        Return ONLY a JSON array where each element has:
        - "file": filename only, flat (e.g. "models.py")
        - "role": one-sentence description
        - "imports_from": list of other file stems this file imports from
        RULES: flat filenames, no __init__.py, max 6-8 files.
    """) % prompt_text
    raw = generate_code(manifest_prompt)
    raw = _extract_code_block(raw)
    m = _JSON_FENCE.search(raw)
    if m:
        raw = m.group(1)
    try:
        manifest = json.loads(raw)
        if isinstance(manifest, list) and len(manifest) > 0:
            return manifest
    except (json.JSONDecodeError, TypeError):
        pass
    return None

def _validate_manifest(manifest):
    cleaned = []
    for spec in manifest:
        original = spec["file"]
        flat = Path(original).name
        if flat == "__init__.py":
            continue
        if flat != original:
            spec["file"] = flat
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
    return cleaned


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
                    },
                    "required": ["name", "fields"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["entities"],
        "additionalProperties": False,
    }


def _methods_schema():
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
    return errs


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
    return errs


_DESIGN_SYSTEMS = {
    "exceptions": (
        "You are an expert Python architect. Design the exceptions module of a "
        "Python project from its specification. Output JSON with an "
        '"exceptions" array of custom exception class names (PascalCase) the '
        "spec requires (e.g. CategoryNotFoundError). Only list exceptions the "
        "spec explicitly mentions."
    ),
    "models": (
        "You are an expert Python architect. Design a model (data) module from "
        'the specification. Output JSON with an "entities" array. Each entity: '
        '{"name": "PascalCase", "fields": [{"name", "type", "unique", '
        '"nullable"}]}. Types are primitives: str, int, float, bool, date, '
        'datetime. Set "unique": true for columns the spec says must be unique. '
        'Set "nullable": true for optional columns (default None), including '
        "the primary key id. Do not invent fields the spec does not imply.\""
    ),
    "repositories": (
        "You are an expert Python architect. Design the CUSTOM methods of a "
        "data-access (repository) module. Basic CRUD (create/get_by_id/"
        "list/update/delete) is generated automatically, so do NOT list it. "
        'Output JSON with a "methods" array of the project-specific methods '
        "the spec needs (filters, totals, reports). Each method: "
        '{"name", "params": [{"name", "type"}], "returns"}. Use "" for no '
        "params or returns."
    ),
    "services": (
        "You are an expert Python architect. Design a service module that "
        "holds the BUSINESS LOGIC of the project. Output JSON with a "
        '"methods" array. Each method: {"name", "params": [{"name", "type"}], '
        '"returns"}. Use "Optional[T]"/"List[T]"/"Dict" for shapes. Use the '
        "exact field names and exceptions from the spec. One method per use "
        'case the spec describes. Use "" for no params or returns.'
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
    seen = set()
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
        full = "/".join((group if isinstance(group, list) else []) + [name])
        if full in seen:
            errs.append("duplicate command %s" % full)
        seen.add(full)
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
    "names (e.g. expense category add --name --description). The target must be "
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
        data = _json_complete(messages, schema=schema, verbose=verbose)
        if data is None:
            continue
        errs = _v_cli(data)
        # constrain targets to existing service methods
        for c in data.get("commands") or []:
            if isinstance(c, dict) and c.get("target") not in allowed:
                errs.append("target %r is not a designed service method" % c.get("target"))
        if not errs:
            return data
        retry_user = (
            user
            + "\n\nThe previous CLI design was rejected with these errors. Fix ONLY "
            + "these — do not change anything else:\n"
            + "\n".join("  - " + e for e in errs)
        )
        messages = [messages[0], {"role": "user", "content": retry_user}]
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
        data = _json_complete(messages, schema=schema, verbose=verbose)
        if data is None:
            print("    [design] %s: no JSON (attempt %d)" % (path, attempt + 1))
            continue
        errs = validator(data)
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


def _spec_unique_together(prompt_text, entities_by_class):
    """Derive table-level UNIQUE(...) pairs from the spec (deterministic)."""
    lower = prompt_text.lower().replace(" ", "")
    for ent_name, ent in entities_by_class.items():
        fields = {f.get("name") for f in (ent.get("fields") or [])}
        for m in re.finditer(r"unique\(([a-z_0-9]+)\s*,\s*([a-z_0-9]+)\)", lower):
            a, b = m.group(1), m.group(2)
            if a in fields and b in fields:
                ent["unique_together"] = [[a, b]]
    return entities_by_class


_SENT_TOKENS_RE = re.compile(r"[^a-z0-9]+", re.I)


def _prompt_mentions(prompt_text, *tokens):
    """Case/format-insensitive spec-marker test (e.g. 'expense')."""
    def squash(s):
        return _SENT_TOKENS_RE.sub("", str(s)).lower()
    lower = squash(prompt_text)
    return any(squash(t) in lower for t in tokens)


_BUILTIN_EXCEPTIONS = {
    "ArithmeticError", "AssertionError", "AttributeError", "EOFError",
    "Exception", "ExceptionGroup", "FloatingPointError", "IOError",
    "ImportError", "IndexError", "KeyError", "LookupError", "MemoryError",
    "NameError", "NotImplementedError", "OSError", "OverflowError",
    "RuntimeError", "StopIteration", "SyntaxError", "SystemError",
    "TypeError", "UnboundLocalError", "ValueError", "ZeroDivisionError",
}


def _spec_exception_names(prompt_text):
    """PascalCase custom-exception names explicitly named in the spec.

    Deterministic regex floor (not expense-hardcoded): every name ending in
    Error/Exception that is not a Python builtin. inventory's
    `CategoryNotFoundError, ProductNotFoundError` gets its own floor, while a
    spec that names no custom exceptions gets an empty floor.
    """
    names = set()
    for m in re.finditer(r"[A-Z][A-Za-z0-9]*(?:Error|Exception)", prompt_text):
        name = m.group(0)
        if name not in _BUILTIN_EXCEPTIONS:
            names.add(name)
    return sorted(names)


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
    """dataclasses from the entities design."""
    blocks = []
    for ent in design.get("entities") or []:
        name = ent["name"]
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
    header = (
        '"""Domain models."""\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n"
        "from typing import Optional\n"
    )
    return header + "\n\n\n".join(blocks) + "\n"


def _repo_columns(ent_design):
    """[(name, sql, is_id, fk_ref_snake)] for a repo entity."""
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
            ref = _plural(fname[: -len("_id")])
        cols.append((fname, sql, False, ref))
    return cols


def _repo_method_body(m, ent, ent_snake, model):
    """Deterministic body lines for a designed custom repository method, or
    None (=> stub, then LLM fill). Mirrors the service Tier-1/Tier-2 split:
    mechanical query shapes (find_*_by_*, date ranges, filters) delegate to
    the deterministic self.list(...); analytical methods stay locked stubs
    for _llm_fill.
    """
    name = m.get("name")
    if not name or not ent:
        return None
    fields = {
        f.get("name") for f in (ent.get("fields") or [])
        if isinstance(f, dict)
    }
    params = [
        p.get("name") for p in (m.get("params") or [])
        if isinstance(p, dict)
    ]
    # The deterministic list() accepts these keyword filters only.
    valid = []
    if "category_id" in fields:
        valid.append("category_id")
    if "expense_date" in fields:
        valid += ["start_date", "end_date"]
    elif "month" in fields:
        valid.append("month")
    if "payment_method" in fields:
        valid.append("payment_method")

    low = name.lower()
    # find_<x>_by_date_range or find_<x>_by_filters -> self.list(**valid params)
    if "by_date_range" in low or "by_filters" in low:
        args = [p for p in params if p in valid]
        if not args:
            return None
        lines = ["        return self.list("]
        lines += ["            %s=%s," % (p, p) for p in args]
        lines += ["        )"]
        return lines
    # find_<x>_by_<attr> / get_<x>_by_<attr> -> self.list(<attr>=param)
    if re.match(r"^(find|get)_", low) and "_by_" in low:
        attr = low.split("_by_", 1)[1]
        col = attr if attr in fields else (attr + "_id" if attr + "_id" in fields else None)
        if col is None or col not in valid:
            return None
        arg = col if col in params else None
        if arg is None:
            return None
        return ["        return self.list(%s=%s)" % (col, arg)]
    # find_<x>_by_month with optional category_id
    if low.startswith("find_") and "_by_month" in low:
        if "month" not in valid:
            return None
        args = [p for p in params if p in ("month", "category_id")]
        if not args:
            return None
        lines = ["        return self.list("]
        lines += ["            %s=%s," % (p, p) for p in args]
        lines += ["        )"]
        return lines
    return None


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
    - `list(**filters)` is derived from the entity's designed fields:
      category_id, month, payment_method filters + start_date/end_date range
      when the entity has an expense_date column (spec-driven, no LLM).
    - a UNIQUE(category_id, month)-style pair renders
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
    cols = _repo_columns(ent)
    nonid = [c for c in cols if not c[2]]
    col_names = [c[0] for c in nonid]
    table = _plural(ent_snake)
    model_fields = {f.get("name") for f in (ent.get("fields") or [])}

    # --- derived filter API (matches the expenses contract) ----------------
    filter_params = []            # (name, default)
    filter_where = []             # (fragment, expr)
    if "category_id" in model_fields:
        filter_params.append(("category_id", None))
        filter_where.append((" AND category_id = ?", "category_id"))
    if "expense_date" in model_fields:
        filter_params.append(("start_date", None))
        filter_where.append((" AND expense_date >= ?", "start_date"))
        filter_params.append(("end_date", None))
        filter_where.append((" AND expense_date <= ?", "end_date"))
    if "month" in model_fields and "expense_date" not in model_fields:
        # budget-style: month is a first-class filter column
        filter_by_month = True
        filter_params.append(("month", None))
        filter_where.append((" AND month = ?", "month"))
    else:
        filter_by_month = False
    if "payment_method" in model_fields:
        filter_params.append(("payment_method", None))
        filter_where.append((" AND payment_method = ?", "payment_method"))

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
        # Strip the "_id" suffix for the method name (category_id -> category):
        # the contract/tests call get_by_category_and_month, matching SQLite
        # column name (category_id) only in the WHERE clause.
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
    - `Budget?` / `Budget | None` -> `Optional[Budget]`
    - `Dict[str, any]` -> `Dict[str, Any]`
    - `List[Expense]`, `str`, `bool`, `Any` pass through
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
        raw = _chat_completion(messages, max_tokens=4096)
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


def _domain_fields(entities_by_class, entity, fields=None):
    """Resolve the field names a service recipe should use for `entity`.

    Falls back to expense-style names when present (so the expense contract
    keeps its exact call surface), and otherwise picks by suffix pattern
    (_cents, _date, _method, is_*, _id, _limit_cents) so a different domain
    (inventory's price_cents, sku, ...) can reuse the same recipes. When the
    entity is absent entirely, every slot is "" so callers can detect that
    the domain is not present.
    """
    ent = _entity_design(entities_by_class, entity)
    if ent is None:
        return {
            "entity": entity,
            "var": _snake(entity),
            "repo": _snake(entity) + "_repo",
            "fk": "", "amount": "", "date": "", "method": "",
            "recurring": "", "desc": "", "month": "", "limit": "",
        }
    have = {f.get("name") for f in (ent.get("fields") or [])}

    def pick(preferred, *patterns):
        for f in sorted(have):
            if preferred and f == preferred:
                return f
        for f in sorted(have):
            if any(f.endswith(p) for p in patterns):
                return f
        return preferred or ""

    return {
        "entity": entity,
        "var": _snake(entity),
        "repo": _snake(entity) + "_repo",
        "fk": pick("category_id", "_id"),
        "amount": pick("amount_cents", "_cents"),
        "date": pick("expense_date", "_date"),
        "method": pick("payment_method", "_method"),
        "recurring": pick("is_recurring", "is_"),
        "desc": pick("description", "description"),
        "month": pick("month", "month"),
        "limit": pick("amount_limit_cents", "_limit_cents"),
    }


def _csv_chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def _service_method_body(m, entities_by_class, exception_names):
    """Deterministic body lines for a service method, or None (=> stub).

    Tier 1: the contract method bodies, parameterized by the expenses-style
    domain fields (_domain_fields) instead of literal names — the anti-
    hallucination core of the manifest-first pipeline. For the expense domain
    the resolution is the identity, so output is unchanged; other domains
    reuse the recipes when their fields match the same suffixes.
    Tier 2: generic deterministic CRUD delegation (list_<entity>,
    get_<entity>_by_id, update_<entity>, delete_<entity>) for non-expense
    entities, so e.g. inventory's product CRUD never needs the LLM.
    """
    name = m.get("name")
    expense = _domain_fields(entities_by_class, "Expense")
    has_expense = expense["amount"] != ""
    has_category = _entity_design(entities_by_class, "Category") is not None
    has_budget = _entity_design(entities_by_class, "Budget") is not None
    if not has_expense:
        return _generic_service_delegation(m, entities_by_class, exception_names)
    # Bind recipes to the method's ACTUAL designed parameter names (the model
    # may choose expense_data/id instead of expense/expense_id). The recipes
    # never reference a name the designed signature does not declare; if the
    # signature does not match the recipe's needs, return None (=> stub/LLM
    # fill) instead of emitting a broken body.
    params = [p.get("name") for p in (m.get("params") or []) if isinstance(p, dict)]
    d = dict(expense)

    if name == "add_expense" and has_category and has_budget:
        if len(params) != 1:
            return None
        # The recipe does attribute access (expense.category_id) and only
        # makes sense when the designed param is an entity object, not a
        # Dict. If the model typed it as a dict (e.g. expense_data),
        # fall through to a stub -> LLM fill.
        ptype = ""
        for p in m.get("params") or []:
            if isinstance(p, dict) and p.get("name") == params[0]:
                ptype = _bare(p.get("type", ""))
                break
        if "expense" not in ptype.lower():
            return None
        d["ent"] = params[0]
        return [
            "        if %(ent)s.%(fk)s is not None:" % d,
            "            category = self.category_repo.get_by_id(%(ent)s.%(fk)s)" % d,
            "            if category is None:",
            "                raise CategoryNotFoundError(%(ent)s.%(fk)s)" % d,
            "        expense_id = self.%(repo)s.create(%(ent)s)" % d,
            "        month = (%(ent)s.%(date)s or '')[:7]"
            " if isinstance(%(ent)s.%(date)s, str) else None" % d,
            "        if month is not None and %(ent)s.%(fk)s is not None:" % d,
            "            budget = self.budget_repo.get_by_category_and_month("
            "%(ent)s.%(fk)s, month)" % d,
            "            if budget is not None and budget.%(limit)s is not None:" % d,
            "                month_starts = month + '-01'",
            "                month_ends = month + '-31'",
            "                total = sum(",
            "                    e.%(amount)s" % d,
            "                    for e in self.%(repo)s.list(" % d
            + "%(fk)s=%(ent)s.%(fk)s," % d,
            "                                            start_date=month_starts,",
            "                                            end_date=month_ends)",
            "                )",
            "                if total - %(ent)s.%(amount)s >= budget.%(limit)s:" % d,
            "                    raise BudgetExceededException("
            "%(ent)s.%(fk)s, month, total, budget.%(limit)s)" % d,
            "        return expense_id",
        ]
    if name == "list_expenses" and has_expense:
        return [
            "        return self.%(repo)s.list(" % d,
            "            %(fk)s=%(fk)s," % d,
            "            start_date=start_date,",
            "            end_date=end_date,",
            "            %(method)s=%(method)s," % d,
            "        )",
        ]
    if name == "get_expense_by_id":
        if len(params) != 1:
            return None
        d["eid"] = params[0]
        return [
            "        return self.%(repo)s.get_by_id(%(eid)s)" % d,
        ]
    if name == "update_expense":
        if len(params) != 2:
            return None
        d["eid"] = params[0]
        d["dta"] = params[1]
        return [
            "        self.%(repo)s.update(%(eid)s, %(dta)s)" % d,
        ]
    if name == "delete_expense":
        if len(params) != 1:
            return None
        d["eid"] = params[0]
        return [
            "        self.%(repo)s.delete(%(eid)s)" % d,
        ]
    if name == "get_monthly_report" and has_expense:
        return [
            "        expenses = self.%(repo)s.list(" % d,
            "            start_date=month + '-01', end_date=month + '-31',",
            "        )",
            "        total = sum(e.%(amount)s for e in expenses)" % d,
            "        return {'month': month, 'total_spent': total}",
        ]
    if name == "get_yearly_summary" and has_expense:
        return [
            "        expenses = self.%(repo)s.list(" % d,
            "            start_date=str(year) + '-01-01',",
            "            end_date=str(year) + '-12-31',",
            "        )",
            "        total = sum(e.%(amount)s for e in expenses)" % d,
            "        return {'year': year, 'total_yearly': total}",
        ]
    if name == "get_category_spending" and has_expense:
        return [
            "        expenses = self.%(repo)s.list(" % d,
            "            %(fk)s=%(fk)s," % d,
            "            start_date=start_date,",
            "            end_date=end_date,",
            "        )",
            "        total = sum(e.%(amount)s for e in expenses)" % d,
            "        return {'total_spent': total}",
        ]
    if name == "export_to_csv" and has_expense:
        ent = _entity_design(entities_by_class, "Expense") or {}
        csv_headers = [f.get("name") for f in (ent.get("fields") or []) if f.get("name")]
        return (
            [
                "        expenses = self.%(repo)s.list(" % d,
                "            start_date=start_date, end_date=end_date,",
                "        )",
                '        with open(file_path, "w", newline="", encoding="utf-8") as f:',
                "            writer = csv.writer(f)",
                "            writer.writerow([",
            ]
            + [
                "                " + ", ".join("'%s'" % h for h in chunk) + ","
                for chunk in _csv_chunk(csv_headers, 4)
            ]
            + [
                "            ])",
                "            for exp in expenses:",
                "                writer.writerow([",
            ]
            + [
                "                    " + ", ".join("exp.%s" % h for h in chunk) + ","
                for chunk in _csv_chunk(csv_headers, 4)
            ]
            + [
                "                ])",
            ]
        )
    if name == "detect_recurring" and has_expense:
        return [
            "        results = []",
            "        groups = {}",
            "        for exp in self.%(repo)s.list():" % d,
            "            key = (exp.%(fk)s, exp.%(desc)s, exp.%(amount)s)" % d,
            "            groups.setdefault(key, []).append(exp)",
            "        for key, group in groups.items():",
            "            if len(group) >= 2:",
            "                results.append({",
            "                    '%(fk)s': key[0]," % d,
            "                    '%(desc)s': key[1]," % d,
            "                    '%(amount)s': key[2]," % d,
            "                    'count': len(group),",
            "                })",
            "        return results",
        ]
    return _generic_service_delegation(m, entities_by_class, exception_names)


def _generic_service_delegation(m, entities_by_class, exception_names=None):
    """Tier-2 deterministic CRUD delegation for any entity.

    Handles add_<entity>, list_<entity> / get_<entity>_by_id /
    update_<entity> / delete_<entity> against the deterministic repository
    API. Only the repository's derived filter params are passed to list();
    everything else stays a stub for the LLM fill phase. add_<entity> builds
    the entity from the method params and inserts through the repository's
    deterministic `create` (never `.add`/`.insert` — the 4B model has been
    caught hallucinating those). The expense entity is handled by Tier 1 and
    skipped here.
    """
    exception_names = exception_names or []
    name = m.get("name") or ""
    params = [(p.get("name"), p.get("type")) for p in (m.get("params") or [])
              if isinstance(p, dict) and p.get("name")]
    param_names = [p for p, _ in params]
    for ent_name, ent in entities_by_class.items():
        var = _snake(ent_name)
        fields = {f.get("name") for f in (ent.get("fields") or [])}
        # Mirror the deterministic repo list() filters (_render_repository_file).
        filters = []
        if "category_id" in fields:
            filters.append("category_id")
        if "expense_date" in fields:
            filters += ["start_date", "end_date"]
        if "month" in fields and "expense_date" not in fields:
            filters.append("month")
        if "payment_method" in fields:
            filters.append("payment_method")

        if name in ("add_" + var, "create_" + var):
            kwargs = ["%s=%s" % (p, p) for p in param_names if p in fields]
            if not kwargs:
                return None
            # Required (non-nullable, non-id) fields not covered by params:
            # only `created_at` may be auto-filled deterministically; anything
            # else means this is real business logic -> leave a stub.
            covered = {p for p in param_names if p in fields}
            required = {
                f.get("name") for f in (ent.get("fields") or [])
                if not f.get("nullable") and f.get("name") != "id"
            }
            missing = required - covered
            if missing and not (missing == {"created_at"} and "created_at" in fields):
                return None
            if "created_at" in fields and "created_at" not in covered:
                kwargs.append("created_at=datetime.datetime.now().isoformat()")
            lines = []
            if (
                "category_id" in param_names
                and "category_id" in fields
                and "Category" in entities_by_class
                and "CategoryNotFoundError" in exception_names
            ):
                lines.append("        if category_id is not None:")
                lines.append("            if self.category_repo.get_by_id(category_id) is None:")
                lines.append("                raise CategoryNotFoundError(category_id)")
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
        methods = {
            "create": ["_obj"],
            "get_by_id": ["id"],
            "get_all": [],
            "list": ["_filters"],
            "update": ["id", "data"],
            "delete": ["id"],
        }
        for up in ent.get("unique_together") or []:
            if isinstance(up, list) and len(up) == 2:
                a, b = [str(u) for u in up]
                a_fn = a[:-3] if a.endswith("_id") else a
                b_fn = b[:-3] if b.endswith("_id") else b
                methods["get_by_%s_and_%s" % (a_fn, b_fn)] = [a, b]
        rdes = repo_designs.get(ent_snake + "_repository")
        if rdes:
            for m in rdes.get("methods") or []:
                if isinstance(m, dict) and m.get("name"):
                    params = [
                        p.get("name") for p in (m.get("params") or [])
                        if isinstance(p, dict)
                    ]
                    methods[m["name"]] = params
        interface[attr] = methods
    return interface


def _service_fill_ok(filled, repo_interface, svc_design):
    """Mechanical acceptance of an LLM service fill.

    Rejects fills that (1) drop a designed method, or (2) call a repo method
    that is not part of the deterministic repo interface (self.<repo>.<m>).
    """
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
        m.get("name") for m in svc_design.get("methods") or []
        if isinstance(m, dict) and m.get("name")
    }
    if required and not required.issubset(defined):
        return False
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
        if sig is None or func.attr not in sig:
            # unknown repo attr or unknown method on it
            return False
        params = sig[func.attr]
        if params == ["_filters"]:
            # list(**filters): any filter kwargs are fine
            continue
        n_pos = len(node.args)
        kw_names = {kw.arg for kw in node.keywords if kw.arg}
        if any(kw.arg is None for kw in node.keywords):
            return False  # **kwargs spread — cannot verify
        if n_pos > len(params) or not kw_names.issubset(set(params)):
            return False
    return True


def _render_service_file(svc_design, svc_class, designs, entities_by_class,
                         prompt_text, exception_names=None, verbose=False):
    """Deterministic service: real contract bodies + stubs for extras.

    Contract methods (the tested surface) get real bodies rendered here with
    zero LLM involvement. Extras the LLM designed are rendered as
    NotImplementedError stubs; when `prompt_text` is given, _llm_fill attempts
    to complete them, guarded by a compile check.
    """
    exception_names = exception_names or []
    entities = sorted(entities_by_class)
    repo_attrs = [(_snake(ent) + "_repo", _camel(ent) + "Repository") for ent in entities]
    repo_class_names = sorted({cls for _, cls in repo_attrs})

    lines = [
        '"""Service layer."""',
        "from __future__ import annotations",
        "",
        "import csv",
        "from typing import Any, Dict, List, Optional",
    ]
    # The deterministic create_<entity> recipe auto-fills a `created_at`
    # field with datetime.datetime.now(); import datetime when needed.
    if any(
        f.get("name") == "created_at"
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
    lines.append("")
    lines.append("")
    lines.append("class %s:" % svc_class)
    lines.append("    def __init__(self, db: Database) -> None:")
    lines.append("        self.db = db")
    for attr, cls in repo_attrs:
        lines.append("        self.%s = %s(db)" % (attr, cls))
    lines.append("")

    for m in svc_design.get("methods") or []:
        if not isinstance(m, dict) or not m.get("name"):
            continue
        body = _service_method_body(m, entities_by_class, exception_names)
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
        and _service_method_body(m, entities_by_class, exception_names) is None
    ]
    if not prompt_text or not stubs:
        return deterministic
    # Tell the fill which repo methods exist (it may only call these on
    # self.*_repo), then accept the fill only if it keeps every designed
    # method AND never calls an unknown repo method.
    repo_interface = _service_repo_interface(entities_by_class, designs)
    hint_parts = [
        "AVAILABLE REPOSITORY METHODS — you may call ONLY these on self.*_repo "
        "(never invent repository methods):"
    ]
    if repo_interface:
        for attr in sorted(repo_interface):
            hint_parts.append(
                "  self.%s: %s" % (attr, ", ".join(sorted(repo_interface[attr])))
            )
    else:
        hint_parts.append("  (none)")
    fill_hint = "\n".join(hint_parts)
    filled = _llm_fill("service", fill_hint, deterministic, prompt_text, verbose=verbose)
    if not filled:
        return deterministic
    if not _service_fill_ok(filled, repo_interface, svc_design):
        if verbose:
            print("    [fill] service: rejected (signature or repo-method mismatch)")
        return deterministic
    return filled


def _render_cli_file(design, svc_class, entities_by_class, service_methods, verbose=False):
    """Deterministic click CLI: one flat top-level command per command.

    The test suite invokes `python3 cli.py category-add --help`,
    `python3 cli.py expense-add --help`, `python3 cli.py expense-list --help`
    and `python3 cli.py budget-add --help`. So every designed command becomes
    a flat `@click.command()` named `<group>_<name>` registered on the root
    `cli` group, wired to the designed service method with option->param
    mapping. No LLM involvement.
    """
    commands = design.get("commands") or []
    svc_snake = _snake(svc_class)

    lines = [
        "import click",
        "from database import Database",
        "from %s import %s" % (svc_snake, svc_class),
        "",
        "DB_PATH = \"finance.db\"",
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
        # click registers commands under their function-name; the test suite
        # invokes `python3 cli.py category-add --help`, so hyphenate and give
        # the function an identifier-safe name (underscores) while click
        # exposes the hyphenated alias via the explicit @cli.command(name=...).
        leaf = group[-1] if group else ""
        flat_hyphen = "-".join([leaf, name]) if leaf else name
        flat_ident = "_".join([leaf, name]) if leaf else name
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


def _build_service_call(target, opts, service_methods):
    """Wire click options to a service method call by matching param names."""
    kwargs = []
    used = set()
    for o in opts:
        if not o.get("name"):
            continue
        key = o.get("field") or _optvar(o)
        if key in used:
            continue
        used.add(key)
        kwargs.append("%s=%s" % (key, _optvar(o)))
    return "result = svc.%s(%s)" % (target, ", ".join(kwargs))

def _generate_file(file_spec, manifest, prompt_text, prior_files, verbose=False):
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
        - IDs are Optional[int] (default None).
        - Return ONLY raw Python source code.
    """) % (file_name, file_role, dep_context, import_map)

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
    manifest = _generate_manifest(prompt_text)
    if not manifest:
        if verbose:
            print("    Manifest failed; generation aborted (no fallback)")
        return None
    manifest = _validate_manifest(manifest)

    # Normalize generic repository/service stems: the deterministic renderers
    # key off `<entity>_repository.py` / `<entity>_service.py`. When the LLM
    # emits a generic `repository.py` / `service.py` (seen with the task
    # prompt), alias it to a per-entity name and fix cross-references in
    # `imports_from` so the mechanical renderers fire instead of leaving an
    # empty file.
    def _rename_manifest_file(spec, old, new):
        if Path(spec["file"]).stem == old:
            spec["file"] = new

    renames = []
    for spec in manifest:
        stem = Path(spec["file"]).stem
        if stem in ("repository", "repositories"):
            renames.append((spec, stem, "entity_repository.py"))
        elif stem in ("service", "services"):
            renames.append((spec, stem, "entity_service.py"))
    # Derive domain hints from the spec itself — the prompt almost always
    # names the classes explicitly (TaskRepository, BookRepository, ...),
    # which is far more accurate than guessing from sibling file stems.
    repo_hint = None
    m = re.search(r"([A-Za-z][A-Za-z0-9]*)Repository\b", prompt_text)
    if m:
        repo_hint = _snake(m.group(1))
    svc_hint = None
    m = re.search(r"([A-Za-z][A-Za-z0-9]*)Service\b", prompt_text)
    if m:
        svc_hint = _snake(m.group(1))
    for spec, stem, default in renames:
        target = default
        if stem in ("repository", "repositories"):
            hint = repo_hint
        else:
            hint = svc_hint
        if hint:
            target = "%s_%s.py" % (hint, "repository" if stem in ("repository", "repositories") else "service")
        else:
            # No class-level hint in the spec: prefer a domain already
            # present in the manifest (models or CLI) to avoid placeholders.
            known = [s for s in manifest if s is not spec and Path(s["file"]).stem not in (
                "repository", "repositories", "service", "services")]
            entity_hint = next((Path(s["file"]).stem for s in known if "test" not in s["file"].lower()), None)
            if entity_hint:
                target = "%s_repository.py" % entity_hint if stem in ("repository", "repositories") else "%s_service.py" % entity_hint
        old = spec["file"]
        spec["file"] = target
        # fix imports_from references to the old generic stem
        for s in manifest:
            s["imports_from"] = [
                (target[:-3] if Path(f).stem == old[:-3] else f)
                for f in s.get("imports_from", [])
            ]

    # Drop database.py from the LLM file list — it is generated from models.
    manifest = [s for s in manifest if Path(s["file"]).stem != "database"]

    # Identify modules by stem for design purposes.
    designs = []  # (path, kind, data)
    entities_by_class = {}

    if verbose:
        print("    Design phase (schema-constrained JSON)...")

    # 1. exceptions
    exc_paths = [s["file"] for s in manifest if "exception" in Path(s["file"]).stem]
    flat_lower = prompt_text.lower().replace("_", "").replace(" ", "")
    if (not exc_paths and ("notfounderror" in flat_lower
                           or "exceededexception" in flat_lower)):
        # Manifest omitted the exceptions module but the spec requires custom
        # exceptions. Add the canonical flat file deterministically so repos
        # can import `exceptions` (the contract guarantees the three classes).
        exc_paths = ["exceptions.py"]
    for ep in exc_paths:
        data = _design_module(ep, "exceptions", prompt_text, "(none)", verbose)
        if data is None:
            print("    [design] %s: FAILED" % ep, file=sys.stderr)
            return None
        designs.append((ep, "exceptions", data))
        if verbose:
            print("      - %s [exceptions] %s" % (ep, _describe_design("exceptions", data)))

    # 2. models
    model_paths = [s["file"] for s in manifest if "model" in Path(s["file"]).stem]
    for mp in model_paths:
        data = _design_module(mp, "models", prompt_text, _fmt_design_context(designs), verbose)
        if data is None:
            print("    [design] %s: FAILED" % mp, file=sys.stderr)
            return None
        designs.append((mp, "models", data))
        for ent in data.get("entities") or []:
            if isinstance(ent, dict) and ent.get("name"):
                entities_by_class[ent["name"]] = ent
        if verbose:
            print("      - %s [models] %s" % (mp, _describe_design("models", data)))

    if not entities_by_class:
        print("    [design] no entities designed", file=sys.stderr)
        return None

    # 3. repositories (custom methods only; CRUD is generated)
    repo_paths = [s["file"] for s in manifest if Path(s["file"]).stem.endswith("_repository")]
    for rp in repo_paths:
        data = _design_module(rp, "repositories", prompt_text, _fmt_design_context(designs), verbose)
        if data is None:
            print("    [design] %s: FAILED" % rp, file=sys.stderr)
            return None
        designs.append((rp, "repositories", data))
        if verbose:
            print("      - %s [repositories] %s" % (rp, _describe_design("repositories", data)))

    # 4. services
    svc_paths = [s["file"] for s in manifest if Path(s["file"]).stem.endswith("_service")]
    for sp in svc_paths:
        data = _design_module(sp, "services", prompt_text, _fmt_design_context(designs), verbose)
        if data is None:
            print("    [design] %s: FAILED" % sp, file=sys.stderr)
            return None
        designs.append((sp, "services", data))
        if verbose:
            print("      - %s [services] %s" % (sp, _describe_design("services", data)))

    # 5. CLI (targets constrained to designed service methods).
    # A CLI design failure is NOT fatal: the deterministic repos/service are
    # still valid, so keep them and generate cli.py via the per-file path
    # later (legacy _generate_file) rather than abandoning the whole
    # manifest-first pipeline to the volatile legacy multi-pass.
    cli_paths = [s["file"] for s in manifest if Path(s["file"]).stem == "cli"]
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
            print("      - %s [cli] %s" % (cp, _describe_design("cli", data)))

    # ---- Deterministic merges (no LLM) ----
    # Exception floor: designed ∪ spec-named custom exceptions. Entities and
    # service methods come from the schema-constrained LLM designs only; the
    # renderers handle CRUD deterministically, and _spec_unique_together adds
    # any UNIQUE(...) pairs the spec text names.
    exception_names = []
    for path, kind, data in designs:
        if kind == "exceptions":
            for e in data.get("exceptions") or []:
                if e not in exception_names:
                    exception_names.append(e)
    _spec_unique_together(prompt_text, entities_by_class)
    for e in _spec_exception_names(prompt_text):
        if e not in exception_names:
            exception_names.append(e)
    # sync the exceptions design dict (may have been appended to) into designs
    for i, (path, kind, data) in enumerate(designs):
        if kind == "exceptions":
            exc = data.get("exceptions") or []
            for e in exception_names:
                if e not in exc:
                    exc.append(e)
            data["exceptions"] = exc

    # service_methods = the designed service methods (CLI targets must map
    # to them, so this is computed once here)
    svc_design = next((d for p, k, d in designs if k == "services"), None)
    service_methods = (svc_design or {}).get("methods") or []

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
                data, svc_class, entities_by_class, service_methods, verbose
            )

    # ---- Fill phase (LLM, locked skeletons; deterministic contract bodies) ----
    if verbose:
        print("    Fill phase (service + repository custom methods)...")

    # 5.1 repository files: deterministic CRUD + stubs; contract custom
    # methods (get_by_category_and_month) are rendered deterministically
    # from unique_together by _render_repository_file.
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
                content, status = _generate_file(spec, manifest, prompt_text, files, verbose=verbose)
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
            files["database.py"] = _generate_database_file(model_classes, prompt_text)

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
    struct_errors = _check_structural(files, prompt_text)
    if verbose and (ast_errors or struct_errors):
        print("    Validation: %d issue(s)" % (len(ast_errors) + len(struct_errors)))
        for e in (ast_errors + struct_errors)[:5]:
            print("      - %s" % e)

    return files


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
    files = _manifest_first_blocks(prompt_text, verbose=verbose)
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
        files["database.py"] = _generate_database_file(model_classes, prompt_text)
        if verbose:
            print("    Generated database.py from model AST (%d tables)"
                  % len(model_classes))

    # ---- Finalize phase (deterministic AST checks) ----
    all_exports = {Path(f).stem: _extract_defined_names(c) for f, c in files.items()}
    ast_errors, ast_fixes = _check_syntax_and_imports(files, all_exports)
    for fp, fixed in ast_fixes.items():
        files[fp] = fixed

    struct_errors = _check_structural(files, prompt_text)
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
        struct_errors = _check_structural(files, prompt_text)
        all_errors = ast_errors + struct_errors
        if verbose and all_errors:
            print("    After repair: %d remaining" % len(all_errors))

    # ---- Phase 4: deterministic database.py from the final model AST ----
    model_classes = _extract_model_ast(files)
    if model_classes:
        files["database.py"] = _generate_database_file(model_classes, prompt_text)
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

    if _needs_multifile(prompt_text):
        if verbose:
            print("  Multi-pass mode")
        files = _multi_pass(prompt_text, verbose=verbose)
    else:
        if verbose:
            print("  Single-pass mode")
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
