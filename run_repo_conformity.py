#!/usr/bin/env python3
"""Prompt -> repository surface conformity gate (deterministic, no LLM).

The counterpart of ``run_cli_conformity.py`` for the layer below it. The CLI
gate answers "does the surface the prompt enumerates exist, and nothing else?";
this one answers "does each repository ship one method per capability, and only
the capabilities the prompt names?".

It is the regression test for the duplicate-capability defect: a repository
method that merely re-spells the deterministic CRUD surface, that extends a
sibling with a scalar qualifier, or whose name appears nowhere in the prompt is
a FAILURE.

Usage:
    python3 run_repo_conformity.py                    # every enumerated prompt
    python3 run_repo_conformity.py --prompt expenses
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from behavior_tests.conformity import prompt_surface_paths
from behavior_tests.repo_conformity import repository_conformity_violations

PROMPTS_DIR = Path("prompts")
GENERATED_ROOT = Path("generated")


def _prompt_ident(path: Path) -> str:
    """``prompts/prompt_library_system.txt`` -> ``library_system``."""
    return path.stem[len("prompt_"):] if path.stem.startswith("prompt_") else path.stem


def _enumerating_prompts() -> list[tuple[str, Path]]:
    """Every prompt that enumerates a command line (hence owns a surface)."""
    out: list[tuple[str, Path]] = []
    for path in sorted(PROMPTS_DIR.glob("prompt_*.txt")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if prompt_surface_paths(text):
            out.append((_prompt_ident(path), path))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", action="append",
                        help="Only check these prompts (repeatable)")
    parser.add_argument("--out", type=Path,
                        default=Path("behavior_runs/repo_conformity"))
    args = parser.parse_args(argv)

    cases = _enumerating_prompts()
    if args.prompt is not None:
        wanted = set(args.prompt)
        cases = [(ident, path) for ident, path in cases if ident in wanted]
    if not cases:
        print("No prompt enumerates a command line.", file=sys.stderr)
        return 1

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {"started_at": datetime.now(timezone.utc).isoformat(), "results": []}
    n_fail = 0
    for ident, path in cases:
        prompt_text = path.read_text(encoding="utf-8")
        project = GENERATED_ROOT / ident
        if not project.is_dir():
            print("[%s] no generated project %s" % (ident, project), file=sys.stderr)
            summary["results"].append({
                "ident": ident, "status": "no_generated",
            })
            n_fail += 1
            continue

        repos = sorted(project.glob("*_repository.py"))
        errs = repository_conformity_violations(prompt_text, project)
        status = "pass" if not errs else "fail"
        if errs:
            n_fail += 1
        out = {
            "ident": ident,
            "generated_dir": str(project),
            "status": status,
            "n_repositories": len(repos),
            "violations": errs,
        }
        (out_dir / ("%s.json" % ident)).write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        print("\n[%s] status=%s repositories=%d violations=%d" % (
            ident, status, len(repos), len(errs)), flush=True)
        for e in errs:
            print("    VIOLATION %s" % e, flush=True)

        summary["results"].append({
            "ident": ident,
            "status": status,
            "n_repositories": len(repos),
            "n_violations": len(errs),
        })

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["failures"] = n_fail
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    print("\n[repo-conformity] failures=%d/%d summary -> %s" % (
        n_fail, len(cases), summary_path))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
