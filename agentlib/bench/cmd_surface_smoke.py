#!/usr/bin/env python3
"""Prompt -> CLI surface smoke gate (deterministic, no LLM).

Answers the third objective directly: **no command the prompt authorizes may
crash**. For every command each enumerating prompt lists, the runner invokes it
three ways — ``--help``, with NO option, and with every option given a
placeholder value — and asserts that stderr never carries a Python traceback
and that the process exits 0 (worked), 1 (a reported domain error) or 2 (click
refused the arguments). A traceback is the defect this guards: the generated
CLI used to let ``CategoryNotFoundError`` and ``sqlite3.IntegrityError`` escape
to the user as a stack dump.

The project tree is COPIED to a scratch directory before the sweep, so the gate
never mutates ``generated/`` and never disturbs the fixtures the other suites
seed.

Usage:
    python3 bench.py surface                  # every enumerated prompt
    python3 bench.py surface --prompt expenses
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from agentlib.bench.conformity import prompt_surface_paths

PROMPTS_DIR = Path("prompts")
GENERATED_ROOT = Path("generated")

# A placeholder per option spelling. Value-less flags are passed bare; the
# sweep only cares that the process never dumps a stack trace.
_INT_PLACEHOLDER = "999"
_STR_PLACEHOLDER = "x"


def _prompt_ident(path: Path) -> str:
    return path.stem[len("prompt_"):] if path.stem.startswith("prompt_") else path.stem


def _enumerating_prompts() -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for path in sorted(PROMPTS_DIR.glob("prompt_*.txt")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if prompt_surface_paths(text):
            out.append((_prompt_ident(path), path))
    return out


def _invocations(options: list[str]) -> list[list[str]]:
    """The three argument vectors every enumerated command is driven with."""
    no_value = {"--recurring", "--available-only", "--active-only", "--low-only"}
    all_args: list[str] = []
    for opt in options:
        if not opt.startswith("--") or "/" in opt:
            continue
        if opt in no_value or opt.startswith("--no-"):
            all_args.append(opt)
        elif opt.endswith(("-id", "-year", "-month")) or opt.endswith("id"):
            all_args.extend([opt, _INT_PLACEHOLDER])
        else:
            all_args.extend([opt, _STR_PLACEHOLDER])
    return [[], ["--help"], all_args]


def _run(project: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "cli.py"] + args,
        cwd=str(project), capture_output=True, text=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", action="append",
                        help="Only smoke these prompts (repeatable)")
    parser.add_argument("--out", type=Path,
                        default=Path("behavior_runs/surface_smoke"))
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
    scratch = Path(tempfile.mkdtemp(prefix="surface_smoke_"))
    try:
        for ident, path in cases:
            source = GENERATED_ROOT / ident
            if not source.is_dir():
                print("[%s] no generated project %s" % (ident, source),
                      file=sys.stderr)
                n_fail += 1
                continue
            project = scratch / ident
            shutil.copytree(source, project)
            for db in project.glob("*.db"):
                db.unlink()

            commands = prompt_surface_paths(path.read_text(encoding="utf-8"))
            violations: list[str] = []
            n_runs = 0
            for command in commands:
                path_args = command["path"].split()
                for extra in _invocations(command.get("options") or []):
                    n_runs += 1
                    proc = _run(project, path_args + extra)
                    if "Traceback (most recent call last)" in (proc.stderr or ""):
                        tail = (proc.stderr or "").strip().splitlines()[-1:]
                        violations.append(
                            "%s %s -> traceback: %s"
                            % (command["path"], " ".join(extra) or "<no option>",
                               tail[0] if tail else "")
                        )
                    elif proc.returncode not in (0, 1, 2):
                        violations.append(
                            "%s %s -> exit=%d (no traceback, but not 0/1/2)"
                            % (command["path"], " ".join(extra) or "<no option>",
                               proc.returncode)
                        )

            status = "pass" if not violations else "fail"
            if violations:
                n_fail += 1
            (out_dir / ("%s.json" % ident)).write_text(
                json.dumps({
                    "ident": ident, "status": status,
                    "n_commands": len(commands), "n_runs": n_runs,
                    "violations": violations,
                }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

            print("\n[%s] status=%s commands=%d runs=%d violations=%d" % (
                ident, status, len(commands), n_runs, len(violations)), flush=True)
            for v in violations:
                print("    VIOLATION %s" % v, flush=True)

            summary["results"].append({
                "ident": ident, "status": status,
                "n_commands": len(commands), "n_runs": n_runs,
                "n_violations": len(violations),
            })
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary["failures"] = n_fail
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    print("\n[surface-smoke] failures=%d/%d summary -> %s" % (
        n_fail, len(cases), summary_path))
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
