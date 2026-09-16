#!/usr/bin/env python3
"""Prompt -> CLI surface conformity gate (deterministic, no LLM).

When a specification ENUMERATES its command line (library_system, expenses,
inventory, ...), the generator must ship EXACTLY that surface: every command
the spec names, under the spec's group path and option names, and nothing
else. This runner checks the GENERATED click CLI against the prompt's own
command list, name for name.

It is the regression test for the "24 commands generated for 9 requested"
defect: a command the prompt never asked for is a FAILURE, and a command the
prompt asked for but that is absent is a FAILURE too.

Usage:
    python3 bench.py cli-conformity                    # every enumerated prompt
    python3 bench.py cli-conformity --prompt expenses
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agentlib.bench.conformity import (
    prompt_surface_paths,
    surface_conformity_violations,
)

PROMPTS_DIR = Path("prompts")
GENERATED_ROOT = Path("generated")


def _prompt_ident(path: Path) -> str:
    """``prompts/prompt_library_system.txt`` -> ``library_system``."""
    return path.stem[len("prompt_"):] if path.stem.startswith("prompt_") else path.stem


def _enumerating_prompts() -> list[tuple[str, Path]]:
    """Every prompt file that itself enumerates a command line."""
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
    parser.add_argument("--out", type=Path, default=Path("behavior_runs/cli_conformity"))
    args = parser.parse_args(argv)

    selected = args.prompt
    cases = _enumerating_prompts()
    if selected is not None:
        wanted = set(selected)
        cases = [(ident, path) for ident, path in cases if ident in wanted]
    if not cases:
        print("No prompt enumerates a command line.", file=sys.stderr)
        return 1

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "results": [],
    }
    n_fail = 0
    for ident, path in cases:
        prompt_text = path.read_text(encoding="utf-8")
        project = GENERATED_ROOT / ident
        wanted_cmds = prompt_surface_paths(prompt_text)
        if not project.is_dir():
            print("[%s] no generated project %s" % (ident, project), file=sys.stderr)
            summary["results"].append({
                "ident": ident, "status": "no_generated",
                "n_prompt_commands": len(wanted_cmds),
            })
            n_fail += 1
            continue
        errs = surface_conformity_violations(prompt_text, project)
        status = "pass" if not errs else "fail"
        if errs:
            n_fail += 1
        out = {
            "ident": ident,
            "generated_dir": str(project),
            "status": status,
            "n_prompt_commands": len(wanted_cmds),
            "prompt_commands": [w["path"] for w in wanted_cmds],
            "violations": errs,
        }
        (out_dir / ("%s.json" % ident)).write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        print("\n[%s] status=%s prompt_commands=%d violations=%d" % (
            ident, status, len(wanted_cmds), len(errs)), flush=True)
        for e in errs:
            print("    VIOLATION %s" % e, flush=True)

        summary["results"].append({
            "ident": ident,
            "status": status,
            "n_prompt_commands": len(wanted_cmds),
            "n_violations": len(errs),
        })

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["failures"] = n_fail
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    print("\n[cli-conformity] failures=%d/%d summary -> %s" % (
        n_fail, len(cases), summary_path))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
