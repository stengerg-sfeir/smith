#!/usr/bin/env python3
"""Run the facade tester end-to-end: map intentions -> execute -> report.

This wires together the NEW facade tester (built ALONGSIDE the existing
internal tester). For each named prompt (plus prompt 20):

1. loads the intent-extraction + facade-discovery artifact
   (``behavior_runs/facade/<ident>.json``, produced by ``run_facade_intents.py``),
2. maps each intention to a concrete CLI invocation (``facade_mapping``),
3. executes it in a subprocess against the generated project
   (``facade_executor``),
4. writes a per-prompt report + a summary under
   ``behavior_runs/facade/execution/``.

It does NOT call the LLM — it reuses the stage-A artifact — so it is fast and
fully deterministic. Unmapped intentions are reported, not run.

Usage:
    python3 run_facade_execution.py                 # all prompts
    python3 run_facade_execution.py --prompt inventory
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from behavior_tests.design_extract import extract_design
from behavior_tests.facade_discovery import discover_facade
from behavior_tests.facade_executor import execute_prompt
from behavior_tests.facade_mapping import map_intentions
from behavior_tests.fixtures import FIXTURES

NAMED = [
    "hello_world", "cli_tool", "inventory", "expenses",
    "library_system", "multi_module",
] + [f"{i:02d}" for i in range(1, 41)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", action="append",
                        help="Only run these prompts (repeatable)")
    parser.add_argument("--out", type=Path, default=Path("behavior_runs/facade/execution"))
    args = parser.parse_args(argv)

    artifact_dir = Path("behavior_runs/facade")
    generated_root = Path("generated")
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    selected = args.prompt
    idents = [i for i in NAMED if selected is None or i in selected]
    if not idents:
        print("No matching prompts.", file=sys.stderr)
        return 1

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "total": len(idents),
        "results": [],
    }

    for ident in idents:
        artifact = artifact_dir / ("%s.json" % ident)
        if not artifact.exists():
            print("[%s] no artifact (run run_facade_intents.py first)" % ident, file=sys.stderr)
            summary["results"].append({"ident": ident, "status": "no_artifact"})
            continue
        data = json.loads(artifact.read_text(encoding="utf-8"))
        intents = data.get("intentions", [])
        proj = generated_root / ident
        if not proj.is_dir():
            print("[%s] no generated project %s" % (ident, proj), file=sys.stderr)
            summary["results"].append({"ident": ident, "status": "no_generated"})
            continue
        facade = discover_facade(proj)  # re-discover (picks up data-dict field keys)

        design = extract_design(proj) if proj.is_dir() else None
        plans = map_intentions(intents, facade, design=design, fixtures=FIXTURES)
        unmapped = [p for p in plans if p["status"] == "unmapped"]
        mapped_all = [p for p in plans if p["status"] == "mapped"]
        mapped = [p for p in mapped_all if not p.get("seed")]
        outcome = execute_prompt(mapped_all, proj, fresh_db=True, fixtures=FIXTURES)
        outcome["unmapped"] = unmapped

        status = "ok"
        if not mapped:
            status = "no_mapped"
        elif outcome["fail"] == 0:
            status = "pass"
        else:
            status = "fail"
        out = {
            "ident": ident,
            "generated_dir": str(proj),
            "status": status,
            "n_intentions": len(intents),
            "n_mapped": len(mapped),
            "n_unmapped": len(unmapped),
            "pass": outcome.get("pass", 0),
            "fail": outcome.get("fail", 0),
            "results": outcome.get("results", []),
            "unmapped": unmapped,
        }
        report = out_dir / ("%s.json" % ident)
        report.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        print("\n[%s] status=%s mapped=%d unmapped=%d pass=%d fail=%d" % (
            ident, status, len(mapped), len(unmapped),
            outcome.get("pass", 0), outcome.get("fail", 0)), flush=True)
        for r in outcome.get("results", []):
            print("    %-4s %-24s %s  %s" % (
                r["status"], r["command"], r["exit_code"], r["reason"]),
                flush=True)
        for u in unmapped:
            print("    UNMAPPED %-20s %s" % (u["intent_id"], u.get("reason", "")), flush=True)

        summary["results"].append({
            "ident": ident,
            "status": status,
            "n_mapped": len(mapped),
            "n_unmapped": len(unmapped),
            "pass": outcome.get("pass", 0),
            "fail": outcome.get("fail", 0),
        })

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary_path = out_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\n[facade-execution] summary -> %s" % summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
