"""Mutation harness: verify the behavioral tests are NOT vacuous.

Correctness verification for the test oracle. We take a generated snapshot,
inject a known bug (a *mutant*) that breaks one of the spec's declared
invariants, re-run the same deterministic behavior tests, and check whether
they now FAIL.

- A mutant that makes the tests fail is KILLED: the tests are correct for
  that invariant.
- A mutant that leaves the tests GREEN SURVIVES: the test is too weak (a
  false pass) for that invariant.

Mutants are *derived from the spec*, not from the code, so this is
non-tautological: each mutant corresponds to an invariant the spec declares
(FK enforcement, unique constraint), and breaking it must be caught.

Usage:
    python3 -m behavior_tests.mutate --prompt 27 [--use-cached-spec]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .oracle import generate_test_spec
from .renderer import render_test_file
from .runner import parse_prompt_number


def _run_test(test_file: Path, root: Path) -> dict | None:
    import os
    env = dict(os.environ)
    env["BEHAVIOR_ROOT"] = str(root.resolve())
    try:
        proc = subprocess.run(
            [sys.executable, str(test_file)],
            cwd=str(test_file.parent),
            capture_output=True,
            text=True,
            env=env,
            timeout=120,
        )
        return json.loads(proc.stdout)
    except (json.JSONDecodeError, subprocess.TimeoutExpired):
        return None


def _mutate_fk_off(snapshot: Path) -> bool:
    """Disable SQLite foreign-key enforcement. Breaks FK integrity."""
    applied = False
    for p in snapshot.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "PRAGMA foreign_keys = ON" in text:
            p.write_text(
                text.replace("PRAGMA foreign_keys = ON", "PRAGMA foreign_keys = OFF"),
                encoding="utf-8",
            )
            applied = True
    return applied


def _mutate_unique_off(snapshot: Path) -> bool:
    """Strip UNIQUE constraints from generated DDL. Breaks uniqueness."""
    applied = False
    for p in snapshot.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\bUNIQUE\b", text, re.IGNORECASE):
            new = re.sub(r"\bUNIQUE\s*\([^)]*\)", "", text, flags=re.IGNORECASE)
            new = new.replace(", UNIQUE", "").replace(" UNIQUE", "")
            new = new.replace("UNIQUE", "")
            if new != text:
                p.write_text(new, encoding="utf-8")
                applied = True
    return applied


def _mutate_sum_zero(snapshot: Path) -> bool:
    """Force aggregation results to zero by neutering `sum(...)` calls."""
    applied = False
    for p in snapshot.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if "sum(" in text:
            p.write_text(text.replace("sum(", "0 + ("), encoding="utf-8")
            applied = True
    return applied


# ---------------------------------------------------------------------------
# Mutant selection is derived from the spec's declared invariants.
# ---------------------------------------------------------------------------

def _mutants_for_spec(spec: dict, snapshot: Path) -> list[dict]:
    mutants = []

    # FK integrity mutant (any entity declares an FK)
    has_fk = any(ent.get("fks") for ent in spec.get("entities", []))
    if has_fk:
        mutants.append({
            "id": "fk_off",
            "label": "disable SQLite FK enforcement",
            "apply": lambda s: _mutate_fk_off(s),
            "expect_domains": ["fk"],
        })

    # Unique constraint mutant (unique field or unique_together)
    has_unique = any(
        (f.get("unique") for ent in spec.get("entities", []) for f in ent.get("fields", []))
        or (ent.get("unique_together") for ent in spec.get("entities", []))
    )
    if has_unique:
        mutants.append({
            "id": "unique_off",
            "label": "strip UNIQUE constraints from DDL",
            "apply": lambda s: _mutate_unique_off(s),
            "expect_domains": ["unique"],
        })

    # sum_equals mutant
    if any(r.get("kind") == "sum_equals" for r in spec.get("business_rules", [])):
        mutants.append({
            "id": "sum_zero",
            "label": "zero the aggregate sums",
            "apply": lambda s: _mutate_sum_zero(s),
            "expect_domains": ["business_rule"],
        })

    return mutants


def mutate_prompt(prompt_path: Path, generated_root: Path, run_dir: Path,
                  use_cached_spec: bool = False) -> dict:
    """Run baseline tests, then each mutant, and record a kill matrix."""
    run_dir.mkdir(parents=True, exist_ok=True)
    number = parse_prompt_number(prompt_path)
    expected_output = generated_root / f"{number:02d}"
    result = {
        "prompt": f"{number:02d}",
        "prompt_file": str(prompt_path),
        "generated_dir": str(expected_output),
        "output_exists": expected_output.is_dir(),
    }
    if not expected_output.is_dir():
        result["status"] = "no_generated_output"
        return result

    # spec (cached or fresh)
    spec_path = run_dir / "test_spec.json"
    spec = None
    if use_cached_spec and spec_path.exists():
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            spec = None
    if spec is None:
        spec = generate_test_spec(prompt_path, spec_path)
    result["test_spec"] = spec_path if spec is not None else None
    if spec is None:
        result["status"] = "oracle_failed"
        return result

    # Render the (deterministic) test file ONCE; run it against each snapshot.
    test_file = run_dir / "test_behavior.py"
    test_file.write_text(render_test_file(spec), encoding="utf-8")

    # Baseline: run against the clean snapshot.
    base_snapshot = run_dir / "baseline_generated"
    if base_snapshot.exists():
        shutil.rmtree(base_snapshot)
    shutil.copytree(expected_output, base_snapshot)
    base_res = _run_test(test_file, base_snapshot)
    base_status = "pass" if base_res and base_res.get("status") == "pass" else "fail"
    result["baseline_status"] = base_status

    # Mutants
    mutants = _mutants_for_spec(spec, base_snapshot)
    rows = []
    for m in mutants:
        mut_root = run_dir / ("mutant_" + m["id"])
        if mut_root.exists():
            shutil.rmtree(mut_root)
        shutil.copytree(expected_output, mut_root)
        applied = m["apply"](mut_root)
        if not applied:
            rows.append({
                "id": m["id"],
                "label": m["label"],
                "applied": False,
                "status": "inapplicable",
            })
            continue
        res = _run_test(test_file, mut_root)
        status = "pass" if res and res.get("status") == "pass" else "fail"
        failures = [
            t["id"] for t in (res or {}).get("tests", [])
            if t.get("status") != "pass"
        ]
        killed = status == "fail"
        rows.append({
            "id": m["id"],
            "label": m["label"],
            "applied": True,
            "status": "killed" if killed else "survived",
            "failing_tests": failures,
        })
    result["mutants"] = rows
    result["status"] = "pass" if all(
        r["status"] in ("killed", "inapplicable") for r in rows
    ) else "fail"
    return result


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", type=Path, default=Path("prompts"))
    parser.add_argument("--generated", type=Path, default=Path("generated"))
    parser.add_argument("--runs", type=Path, default=Path("behavior_runs"))
    parser.add_argument("--prompt", type=int, action="append")
    parser.add_argument("--use-cached-spec", action="store_true")
    argv = parser.parse_args(args)

    prompts_dir, generated_root, runs_dir = (
        argv.prompts.resolve(), argv.generated.resolve(), argv.runs.resolve(),
    )
    prompt_nums = argv.prompt or []
    prompts = []
    for p in sorted(prompts_dir.glob("prompt_*.txt")):
        n = parse_prompt_number(p)
        if n is None:
            continue
        if prompt_nums and n not in prompt_nums:
            continue
        prompts.append(p)
    if not prompts:
        print("No prompts matched")
        return 1

    for prompt_path in prompts:
        n = parse_prompt_number(prompt_path)
        run_dir = runs_dir / f"{n:03d}_mut"
        print("\n--- Mutation prompt %02d ---" % n, flush=True)
        res = mutate_prompt(prompt_path, generated_root, run_dir,
                            use_cached_spec=argv.use_cached_spec)
        print("  baseline=%s" % res.get("baseline_status"))
        for m in res.get("mutants", []):
            print("  mutant %-12s -> %s%s" % (
                m["id"], m["status"],
                (" (fails: %s)" % ",".join(m["failing_tests"])) if m["failing_tests"] else "",
            ))
        (run_dir / "mutation_result.json").write_text(
            json.dumps(res, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
