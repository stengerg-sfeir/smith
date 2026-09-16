#!/usr/bin/env python3
"""Run the full facade tester over ALL prompts in batches of 5.

Two stages per prompt, matching ``bench facade-intents`` then
``bench facade-exec``:

- Stage A: extract intentions + discover the CLI facade -> writes
  ``behavior_runs/facade/<ident>.json``.
- Stage C+D: map intentions -> execute -> writes
  ``behavior_runs/facade/execution/<ident>.json``.

The prompts are processed in batches of 5. After each batch the per-prompt
artifacts and a batch summary are written to ``behavior_runs/facade/batches/``,
so a partial run is never lost.

Usage:
    python3 bench.py facade-all                  # all prompts, batches of 5
    python3 bench.py facade-all --only 01 02 03  # only these idents
    python3 bench.py facade-all --batch-size 3
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from agentlib.bench.cmd_facade_intents import NAMED as INTENT_NAMED

ALL_IDENTS = [alias for alias, _pf, _gd in INTENT_NAMED]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="*",
                        help="Only run these idents")
    parser.add_argument("--batch-size", type=int, default=5,
                        help="Prompts per batch (default 5)")
    parser.add_argument("--out", type=Path,
                        default=Path("behavior_runs/facade/batches"))
    args = parser.parse_args(argv)

    idents = args.only or ALL_IDENTS
    if not idents:
        print("No prompts to run.", file=sys.stderr)
        return 1

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    batch_size = max(1, args.batch_size)
    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "batch_size": batch_size,
        "total_prompts": len(idents),
        "batches": [],
    }

    for start in range(0, len(idents), batch_size):
        batch = idents[start:start + batch_size]
        print("\n===== BATCH %d (%s) =====" % (
            start // batch_size + 1, ", ".join(batch)), flush=True)

        # Stage A: intents + facade discovery
        a_cmd = [sys.executable, "bench.py", "facade-intents"]
        for ident in batch:
            a_cmd += ["--prompt", ident]
        a = subprocess.run(a_cmd, check=False)

        # Stage C+D: map + execute
        e_cmd = [sys.executable, "bench.py", "facade-exec"]
        for ident in batch:
            e_cmd += ["--prompt", ident]
        e = subprocess.run(e_cmd, check=False)

        batch_summary = {
            "batch": start // batch_size + 1,
            "idents": batch,
            "stages_exit": {"intents": a.returncode, "execution": e.returncode},
            "written_at": datetime.now(timezone.utc).isoformat(),
        }
        summary["batches"].append(batch_summary)
        batch_file = out_dir / ("batch_%02d.json" % batch_summary["batch"])
        batch_file.write_text(
            json.dumps(batch_summary, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print("  batch artifact -> %s" % batch_file, flush=True)

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("\n[facade-all] summary -> %s" % summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
