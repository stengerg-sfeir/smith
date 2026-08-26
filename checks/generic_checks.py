#!/usr/bin/env python3
"""Generic checks. No prompt-specific semantic judgment."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path


def syntax_check(root: Path) -> dict:
    files = list(root.rglob("*.py"))
    errors = []

    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception as exc:
            errors.append({"file": str(path), "error": str(exc)})

    return {
        "status": "pass" if files and not errors else "fail",
        "python_files": len(files),
        "errors": errors,
    }


def not_implemented_check(root: Path) -> dict:
    matches = []

    for path in root.rglob("*.py"):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(lines, start=1):
            if "NotImplementedError" in line:
                matches.append({
                    "file": str(path),
                    "line": line_number,
                    "text": line.strip(),
                })

    return {
        "status": "pass" if not matches else "fail",
        "count": len(matches),
        "matches": matches,
    }

def empty_python_check(root: Path) -> dict:
    matches = []

    for path in root.rglob("*.py"):
        try:
            if not path.read_text(encoding="utf-8").strip():
                matches.append(str(path))
        except UnicodeDecodeError:
            matches.append(str(path))

    return {
        "status": "pass" if not matches else "fail",
        "files": matches,
    }


def compile_check(root: Path) -> dict:
    errors = []

    for path in root.rglob("*.py"):
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            errors.append({
                "file": str(path),
                "stderr": proc.stderr[-2000:],
            })

    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }



def internal_import_check(root: Path) -> dict:
    """Check that relative/local imports resolve to files in the project.

    This is deliberately conservative: third-party imports are not treated
    as failures because dependencies may legitimately be installed outside
    the generated project.
    """
    errors = []

    py_files = {p.resolve(): p for p in root.rglob("*.py")}
    package_dirs = {p.resolve() for p in root.rglob("__init__.py")}

    def resolve_module(module: str, source: Path) -> bool:
        parts = module.split(".")
        base = source.parent.resolve()

        # Resolve absolute imports against the generated project root.
        candidates = [
            root.joinpath(*parts).with_suffix(".py"),
            root.joinpath(*parts, "__init__.py"),
        ]

        # Also support imports relative to the source package.
        for package_dir in package_dirs:
            try:
                rel = source.parent.resolve().relative_to(package_dir.parent)
            except ValueError:
                continue
            candidates.extend([
                package_dir.parent.joinpath(*parts).with_suffix(".py"),
                package_dir.parent.joinpath(*parts, "__init__.py"),
            ])

        return any(p.resolve() in py_files for p in candidates if p.exists())

    for path in py_files.values():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except Exception:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # Only flag imports whose top-level name clearly maps to a
                # generated module/package.
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if (root / top).exists() or (root / f"{top}.py").exists():
                        if not resolve_module(alias.name, path):
                            errors.append({
                                "file": str(path),
                                "line": node.lineno,
                                "import": alias.name,
                            })

            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                top = node.module.split(".")[0]
                if (root / top).exists() or (root / f"{top}.py").exists():
                    if not resolve_module(node.module, path):
                        errors.append({
                            "file": str(path),
                            "line": node.lineno,
                            "import": node.module,
                        })

    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }


def runtime_import_check(root: Path) -> dict:
    """Import every generated Python module in an isolated subprocess.

    This catches missing local imports and import-time exceptions that
    py_compile cannot detect. Modules whose import requires a special runtime
    environment may legitimately fail; those failures are intentionally
    visible to the benchmark rather than hidden.
    """
    errors = []
    modules = []

    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if path.name == "__init__.py":
            module = ".".join(rel.parent.parts)
        else:
            module = ".".join(rel.with_suffix("").parts)

        if module.endswith("."):
            module = module[:-1]

        if module and module != "__init__":
            modules.append((path, module))

    for path, module in modules:
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, importlib; importlib.import_module(sys.argv[1])",
                module,
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode != 0:
            errors.append({
                "file": str(path),
                "module": module,
                "stderr": proc.stderr[-2000:],
            })

    return {
        "status": "pass" if not errors else "fail",
        "modules": len(modules),
        "errors": errors,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: generic_checks.py GENERATED_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()

    if not root.is_dir():
        print(json.dumps({
            "status": "fail",
            "reason": "directory_not_found",
        }))
        return 1

    checks = {
        "syntax": syntax_check(root),
        "not_implemented": not_implemented_check(root),
        "empty_python_files": empty_python_check(root),
        "compile": compile_check(root),
        "internal_imports": internal_import_check(root),
        "runtime_imports": runtime_import_check(root),
    }

    # All generic integrity/completeness checks are hard gates.
    # No prompt-specific semantic judgment is performed here.
    overall = "pass" if all(
        item["status"] == "pass"
        for item in checks.values()
    ) else "fail"

    print(json.dumps({
        "overall": overall,
        "checks": checks,
    }, indent=2, ensure_ascii=False))

    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
