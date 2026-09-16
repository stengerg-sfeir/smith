#!/usr/bin/env python3
"""Extract user intentions + discover the CLI facade for the named prompts.

This is the first slice of the NEW "facade" tester, built ALONGSIDE the
existing internal tester (``bench behavior``). It does NOT replace or
touch the existing runner; it only:

1. extracts USER INTENTIONS from each named prompt (``intents.extract_intentions``),
2. discovers the real CLI FACADE from the generated project
   (``facade_discovery.discover_facade``),
3. writes a JSON artifact per prompt under ``behavior_runs/facade/``.

It deliberately stops before mapping intentions to concrete invocations
(stage C) and running them (stage D) — those come next. This run produces the
reference artifact that tells us, per prompt, which intentions are
explicitly/partially/vaguely specified and what the actual CLI surface is.

Usage:
    python3 bench.py facade-intents                 # all named prompts + 20
    python3 bench.py facade-intents --prompt inventory
    python3 bench.py facade-intents --prompt cli_tool --prompt hello_world
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agentlib.bench.facade_discovery import discover_facade
from agentlib.bench.intents import extract_intentions

# Named prompts the generator ships. Numeric prompts 01-40 are appended below
# (each maps to prompts/prompt_XX.txt and generated/XX).
NAMED = [
    ("hello_world", "prompt_hello_world.txt", "hello_world"),
    ("cli_tool", "prompt_cli_tool.txt", "cli_tool"),
    ("inventory", "prompt_inventory.txt", "inventory"),
    ("expenses", "prompt_expenses.txt", "expenses"),
    ("library_system", "prompt_library_system.txt", "library_system"),
    ("multi_module", "prompt_multi_module.txt", "multi_module"),
]
NAMED += [
    (f"{i:02d}", f"prompt_{i:02d}.txt", f"{i:02d}")
    for i in range(1, 41)
]


def build_ident(prompt_alias: str, prompt_file: str, gen_dir: str) -> dict:
    prompts_dir = Path("prompts")
    generated_dir = Path("generated")
    prompt_path = prompts_dir / prompt_file
    project_dir = generated_dir / gen_dir
    prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else ""
    return {
        "alias": prompt_alias,
        "prompt_file": str(prompt_path),
        "generated_dir": str(project_dir),
        "prompt_text": prompt_text,
        "prompt_exists": prompt_path.exists(),
        "generated_exists": project_dir.is_dir(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", action="append",
                        help="Only process these prompt aliases (repeatable)")
    parser.add_argument("--out", type=Path, default=Path("behavior_runs/facade"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    selected = args.prompt
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    entries = [e for e in NAMED if selected is None or e[0] in selected]
    if not entries:
        print("No matching named prompts.", file=sys.stderr)
        return 1

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total": len(entries),
        "results": [],
    }

    for alias, prompt_file, gen_dir in entries:
        info = build_ident(alias, prompt_file, gen_dir)
        ident = alias
        print("\n[facade] %s" % ident, flush=True)
        print("  prompt:   %s" % info["prompt_file"])
        print("  generated:%s" % info["generated_dir"])
        if not info["prompt_exists"]:
            print("  !! prompt file missing", file=sys.stderr)
            summary["results"].append({
                "ident": ident,
                "status": "prompt_missing",
            })
            continue

        intents = extract_intentions(info["prompt_text"], verbose=args.verbose)
        print("  intents:  %d (spec_level: %s)" % (
            len(intents),
            ", ".join(sorted({i["spec_level"] for i in intents})) or "none",
        ))

        facade = {"entry": "", "kind": "none", "commands": [], "invoker": ""}
        if info["generated_exists"]:
            facade = discover_facade(Path(info["generated_dir"]))
            print("  facade:   kind=%s entry=%s commands=%d" % (
                facade["kind"], facade["entry"], len(facade["commands"])),
            )
        else:
            print("  facade:   (no generated project)")

        payload = {
            "ident": ident,
            "prompt_file": info["prompt_file"],
            "generated_dir": info["generated_dir"],
            "prompt": info["prompt_text"],
            "intentions": intents,
            "facade": facade,
            "generated_exists": info["generated_exists"],
            "status": "ok",
        }
        artifact = out_dir / ("%s.json" % ident)
        artifact.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        summary["results"].append({
            "ident": ident,
            "status": "ok",
            "n_intents": len(intents),
            "spec_levels": sorted({i["spec_level"] for i in intents}),
            "facade_kind": facade["kind"],
            "facade_commands": len(facade["commands"]),
        })
        print("  wrote:    %s" % artifact)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary_file = out_dir / "summary.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("\n[facade] summary -> %s" % summary_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
