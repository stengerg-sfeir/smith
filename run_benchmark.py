#!/usr/bin/env python3
"""Sequential benchmark runner for the neurosymbolic agent."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def parse_prompt_number(path: Path) -> int | None:
    try:
        return int(path.stem.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def run_checks(checker: Path, generated_dir: Path) -> tuple[int, dict | None]:
    if not generated_dir.is_dir():
        return 1, {"status": "fail", "reason": "generated_output_missing"}

    proc = subprocess.run(
        [sys.executable, str(checker), str(generated_dir)],
        capture_output=True,
        text=True,
    )

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {
            "status": "checker_error",
            "exit_code": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
        }

    return proc.returncode, data


def run_one(agent: Path, checker: Path, prompt_file: Path,
            generated_root: Path, run_dir: Path, clean_output: bool) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)

    number = parse_prompt_number(prompt_file)
    if number is None:
        raise ValueError(f"Invalid prompt filename: {prompt_file}")

    shutil.copy2(prompt_file, run_dir / "prompt.txt")

    # Agent outputs live at generated/<NN> (e.g. generated/02), matching
    # the "--prompt NN" argument passed below - not generated/prompt_NN.
    expected_output = generated_root / f"{number:02d}"

    if clean_output and expected_output.exists():
        shutil.rmtree(expected_output)

    log_file = run_dir / "agent.log"

    cmd = [sys.executable, str(agent), "--prompt", f"{number:02d}"]

    started_at = datetime.now(timezone.utc).isoformat()
    started = time.monotonic()

    with log_file.open("w", encoding="utf-8") as log:
        log.write("$ " + " ".join(map(str, cmd)) + "\n\n")
        proc = subprocess.run(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    duration = round(time.monotonic() - started, 3)

    generation_status = "success" if proc.returncode == 0 else "failed"

    # Freeze the generated result for this benchmark run.
    captured_dir = run_dir / "generated"
    output_exists = expected_output.is_dir()

    if output_exists:
        # Re-runs over an existing snapshot must overwrite it: copytree
        # raises FileExistsError when the destination already exists,
        # which would abort the refresh and freeze a STALE run (old
        # result.json keeps failing even after the agent is fixed).
        if captured_dir.exists():
            shutil.rmtree(captured_dir)
        shutil.copytree(expected_output, captured_dir)

    checks = None
    checks_exit = None

    if output_exists:
        checks_exit, checks = run_checks(checker, captured_dir)

    result = {
        "prompt": f"{number:02d}",
        "prompt_file": str(prompt_file),
        "started_at": started_at,
        "duration_seconds": duration,
        "agent": {
            "command": " ".join(map(str, cmd)),
            "exit_code": proc.returncode,
            "generation_status": generation_status,
        },
        "output": {
            "expected": str(expected_output),
            "exists": output_exists,
            "captured": output_exists,
        },
        "checks": checks,
        "checks_exit_code": checks_exit,
        "log": str(log_file),
    }

    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", type=Path, default=Path("agent.py"))
    parser.add_argument("--prompts", type=Path, default=Path("prompts"))
    parser.add_argument("--runs", type=Path, default=Path("runs"))
    parser.add_argument("--generated", type=Path, default=Path("generated"))
    parser.add_argument(
        "--checker",
        type=Path,
        default=Path("checks/generic_checks.py"),
    )
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not delete an existing generated/prompt_XX before running.",
    )
    args = parser.parse_args()

    agent = args.agent.resolve()
    prompts_dir = args.prompts.resolve()
    runs_dir = args.runs.resolve()
    generated_root = args.generated.resolve()
    checker = args.checker.resolve()

    prompts = []
    for path in sorted(prompts_dir.glob("prompt_*.txt")):
        n = parse_prompt_number(path)
        if n is None:
            continue
        if args.start is not None and n < args.start:
            continue
        if args.end is not None and n > args.end:
            continue
        prompts.append((n, path))

    if not prompts:
        print(f"No prompts found in {prompts_dir}")
        return 1

    runs_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "agent": str(agent),
        "prompts_dir": str(prompts_dir),
        "generated_root": str(generated_root),
        "total": len(prompts),
        "generation": {"success": 0, "failed": 0},
        "output": {"present": 0, "missing": 0},
        "checks": {"pass": 0, "fail": 0, "not_run": 0},
        "results": [],
    }

    print("=" * 64)
    print(f"Benchmark: {len(prompts)} prompt(s)")
    print(f"Agent:     {agent}")
    print(f"Generated: {generated_root}")
    print("=" * 64)

    for index, (_, prompt_file) in enumerate(prompts, 1):
        number = parse_prompt_number(prompt_file)
        run_dir = runs_dir / f"{number:03d}"

        print(f"\n[{index}/{len(prompts)}] Prompt {number:02d}", flush=True)

        result = run_one(
            agent=agent,
            checker=checker,
            prompt_file=prompt_file,
            generated_root=generated_root,
            run_dir=run_dir,
            clean_output=not args.no_clean,
        )

        summary["results"].append(result)

        if result["agent"]["generation_status"] == "success":
            summary["generation"]["success"] += 1
        else:
            summary["generation"]["failed"] += 1

        if result["output"]["exists"]:
            summary["output"]["present"] += 1
        else:
            summary["output"]["missing"] += 1

        if result["checks"] is None:
            summary["checks"]["not_run"] += 1
            check_label = "NOT RUN"
        elif result["checks_exit_code"] == 0:
            summary["checks"]["pass"] += 1
            check_label = "PASS"
        else:
            summary["checks"]["fail"] += 1
            check_label = "FAIL"

        print(
            f"  generation={result['agent']['generation_status'].upper()} "
            f"output={'YES' if result['output']['exists'] else 'NO'} "
            f"checks={check_label} "
            f"time={result['duration_seconds']}s",
            flush=True,
        )

    summary["finished_at"] = datetime.now(timezone.utc).isoformat()

    summary_file = runs_dir / "summary.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"Generation: {summary['generation']['success']} pass / "
          f"{summary['generation']['failed']} fail")
    print(f"Output:     {summary['output']['present']} present / "
          f"{summary['output']['missing']} missing")
    print(f"Checks:     {summary['checks']['pass']} pass / "
          f"{summary['checks']['fail']} fail / "
          f"{summary['checks']['not_run']} not run")
    print(f"Summary:    {summary_file}")

    return 0 if summary["generation"]["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
