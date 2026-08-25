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
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        if "NotImplementedError" in text:
            matches.append(str(path))

    return {
        "status": "pass" if not matches else "fail",
        "files": matches,
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
    }

    overall = "pass" if all(
        item["status"] == "pass" for item in checks.values()
    ) else "fail"

    print(json.dumps({
        "overall": overall,
        "checks": checks,
    }, indent=2, ensure_ascii=False))

    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
