"""AST-based deterministic utilities and structural validation.

Extracted from agent.py. These run with zero LLM cost: syntax checks, import
resolution, structural design-driven validation, and model-class extraction.
"""
import ast
import re
from pathlib import Path


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
    exc_fps = [
        fp for fp in (design_ctx.get("exception_files") or []) if fp in files
    ] or [fp for fp in files if "exception" in fp.lower()]
    exc_hint = exc_fps[0] if exc_fps else next(iter(files), "exceptions.py")
    for exc in design_ctx.get("exceptions") or []:
        if "class %s" % exc not in all_code:
            errors.append("%s: missing required exception '%s'" % (exc_hint, exc))

    # 2. Designed entity classes + fields
    model_fps = [
        fp for fp in (design_ctx.get("model_files") or []) if fp in files
    ] or [fp for fp in files if "model" in fp.lower()]
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


def _extract_model_ast(files, paths=None):
    """Extract model class definitions from model files.

    Returns dict of class_name -> list of (field_name, python_type_hint).
    Handles annotation-assignment (`field: type = default`), plain
    assignment, and __init__-based field definitions. Also captures the
    UNIQUE_TOGETHER constant into result["__unique_together__"] and the
    TABLE_NAMES constant into result["__table_names__"] when present.
    """
    result = {}
    # Explicit model paths (from the layout design) win over filename
    # sniffing: a models module named task.py must never be invisible to
    # DDL generation just because its name lacks "model".
    if paths is not None:
        model_files = [p for p in paths if p in files]
    else:
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
