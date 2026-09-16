"""Runner for the executed semantic oracle and its mutation validation.

Two questions, answered for each target project:

  * does the generated project SATISFY the invariants (the executed oracle)?
  * is the oracle LOAD-BEARING? The mutation harness must break every
    invariant when the behaviour it observes is stubbed; an invariant that
    survives its own mutation proves nothing.

Usage:
    python3 bench.py semantic
    python3 bench.py semantic --project expenses
    python3 bench.py semantic --no-mutate
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .mutate_semantic import mutate
from .semantic_oracle import run

# Projects the semantic oracle has spec invariants for. A project without an
# entry is reported, never silently skipped.
DEFAULT_PROJECTS = ("library_system", "expenses")


def _run_oracle(root):
    try:
        return run(root)
    except SystemExit as exc:
        return {
            "project": root.name,
            "status": "fail",
            "total": 0,
            "passed": 0,
            "tests": [],
            "error": str(exc),
        }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project", action="append", default=None,
        help="project name(s); repeatable (default: all targets)",
    )
    parser.add_argument("--generated", type=Path, default=Path("generated"))
    parser.add_argument(
        "--no-mutate", action="store_true",
        help="skip the mutation validation",
    )
    args = parser.parse_args(argv)

    projects = args.project or list(DEFAULT_PROJECTS)
    failures = []
    for project in projects:
        root = args.generated / project
        if not root.is_dir():
            print("%s: SKIP (no generated output at %s)" % (project, root))
            failures.append("%s missing" % project)
            continue
        res = _run_oracle(root)
        for test in res["tests"]:
            if test["status"] != "pass":
                print(
                    "  FAIL [%-6s] %s -> %s"
                    % (test["family"], test["id"], test.get("detail", ""))
                )
        if res.get("error"):
            print("  ERROR %s -> %s" % (project, res["error"]))
            failures.append("%s oracle" % project)
            continue
        print("%s: %d/%d invariant(s) hold" % (
            project, res["passed"], res["total"]))
        if res["status"] != "pass":
            failures.append("%s oracle" % project)
        if args.no_mutate:
            continue
        mut = mutate(project, args.generated, verbose=False)
        print("%s: mutation %s (baseline %s/%s)" % (
            project, mut["status"], mut.get("baseline_passed"),
            mut.get("baseline_total")))
        if mut["status"] != "pass":
            failures.append("%s mutation" % project)
    if failures:
        print("FAILED: %s" % ", ".join(failures))
        return 1
    print("ALL SEMANTIC CHECKS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
