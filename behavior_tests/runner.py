"""Runner: orchestrates the behavioral test pipeline for one or more prompts.

This is independent of ``run_benchmark.py``. For each prompt it:

1. extracts a ``test_spec.json`` (the test oracle — one LLM pass),
2. renders a deterministic ``test_behavior.py``,
3. runs it against the generated project in a subprocess,
4. parses the JSON result and folds per-test pass/fail + a coverage matrix
   into a result dict.

The runner can be used standalone (``python3 run_behavior_tests.py``) and is
deliberately not coupled to the generation benchmark.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .oracle import extract_business_rules, generate_test_spec
from .renderer import render_test_file
from .design_extract import extract_design
from .conformity import check_conformity
from .spec_schema import normalize_test_spec, v_test_spec


def parse_prompt_number(path: Path) -> int | None:
    try:
        return int(path.stem.split("_", 1)[1])
    except (IndexError, ValueError):
        return None


def parse_prompt_ident(path: Path) -> str | None:
    """Return the prompt identifier: the number ('27') or name ('hello_world')."""
    stem = path.stem
    if "_" in stem:
        return stem.split("_", 1)[1]
    return None


def run_single(prompt_path: Path, generated_root: Path, run_dir: Path,
               use_cached_spec: bool = False, verbose: bool = False,
               use_design: bool = False) -> dict:
    """Run the behavioral test pipeline for one prompt.

    ``generated_root`` is where ``agent.py --prompt NN`` writes its output
    (e.g. ``generated/27``). The prompt's generated project is frozen into
    ``run_dir/generated`` (a copy) so the run is reproducible against a known
    snapshot, and the ``test_spec.json`` + ``test_behavior.py`` are stored
    alongside it.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    ident = parse_prompt_ident(prompt_path)
    if ident is None:
        raise ValueError("Invalid prompt filename: %s" % prompt_path)

    shutil.copy2(prompt_path, run_dir / "prompt.txt")

    expected_output = generated_root / ident
    result = {
        "prompt": ident,
        "prompt_file": str(prompt_path),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "generated_dir": str(expected_output),
        "output_exists": expected_output.is_dir(),
    }

    if not expected_output.is_dir():
        result["status"] = "no_generated_output"
        result["tests"] = []
        result["coverage"] = {}
        return result

    # Freeze the generated snapshot for this behavioral run.
    captured = run_dir / "generated"
    if captured.exists():
        shutil.rmtree(captured)
    shutil.copytree(expected_output, captured)

    # 1. Test spec. Two sources: the design-based path (named projects) or the
    #    fresh-prompt oracle (numbered prompts).
    spec_path = run_dir / "test_spec.json"
    spec = None
    if use_design:
        # Reconstruct the produced design (names == code names, so no drift),
        # gate it for conformity with the prompt, and use it as the spec ONLY
        # if it conforms. This is the anti-tautology guard.
        design = extract_design(captured)
        prompt_text = prompt_path.read_text(encoding="utf-8")
        conformity = check_conformity(prompt_text, design, captured, verbose=verbose)
        result["conformity"] = conformity
        run_dir.joinpath("design.json").write_text(
            json.dumps(design, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if conformity.get("conforms"):
            # The gate saw the full design (including cli); the spec schema
            # only understands entities/exceptions/repositories/services, so
            # strip the extra 'cli' key before conversion.
            testable = {k: v for k, v in design.items() if k != "cli"}
            spec = normalize_test_spec(testable)
            # Merge the dedicated kind-detection pass into the design based
            # spec so the business rules the prompt implies are detected by a
            # focused oracle (lower cognitive load) rather than the full spec
            # oracle, which tends to miss them.
            kind_oracle = extract_business_rules(prompt_text, verbose=verbose)
            if kind_oracle is not None:
                entity_names = {e["name"] for e in spec.get("entities", [])}
                repo_svc_classes = {
                    o.get("class") for o in
                    (spec.get("repositories", []) + spec.get("services", []))
                }

                def _rule_target_exists(rule):
                    """True if every entity/class target the rule names exists
                    in the design-based spec. The dedicated oracle reads only
                    the prompt, so it may invent a target (entity/class) with
                    no counterpart in the generated design; such a rule cannot
                    be exercised and would only cause a spurious FAIL."""
                    for key in ("entity", "parent_entity", "child_entity",
                                "ref_entity"):
                        val = rule.get(key)
                        if val and val not in entity_names:
                            return False
                    cls = rule.get("class")
                    if cls and cls not in repo_svc_classes:
                        return False
                    return True

                merged = list(spec.get("business_rules", []))
                unexpressed = list(kind_oracle.get("unexpressed_rules", []))
                for rule in kind_oracle.get("business_rules", []):
                    if not _rule_target_exists(rule):
                        unexpressed.append(
                            "Rule %s (%s): target not present in the generated "
                            "design" % (rule.get("id"), rule.get("kind"))
                        )
                        continue
                    if not any(r.get("id") == rule.get("id") for r in merged):
                        merged.append(rule)
                spec["business_rules"] = merged
                spec["business_logic_coverage"] = kind_oracle.get(
                    "business_logic_coverage", "full")
                spec["unexpressed_rules"] = unexpressed
        else:
            result["status"] = "conformity_failed"
            result["tests"] = []
            result["coverage"] = {}
            result["finished_at"] = datetime.now(timezone.utc).isoformat()
            return result
    else:
        if use_cached_spec and spec_path.exists():
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                spec = None
        if spec is None:
            spec = generate_test_spec(prompt_path, spec_path, verbose=verbose)

    result["test_spec"] = str(spec_path) if spec is not None else None
    if spec is None:
        result["status"] = "oracle_failed"
        result["tests"] = []
        result["coverage"] = {}
        return result

    # Surface business-logic coverage (full|partial|none) + unexpressed rules.
    result["business_logic_coverage"] = spec.get("business_logic_coverage", "full")
    result["unexpressed_rules"] = spec.get("unexpressed_rules", [])
    # Persist the (possibly merged) spec alongside the run for reproducibility.
    spec_path.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # 2. Deterministic render.
    test_file = run_dir / "test_behavior.py"
    test_file.write_text(render_test_file(spec), encoding="utf-8")

    # 3. Execute against the frozen snapshot.
    env = dict(**__import__("os").environ)
    env["BEHAVIOR_ROOT"] = str(captured.resolve())
    proc = subprocess.run(
        [sys.executable, str(test_file)],
        cwd=str(run_dir),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    parsed = None
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        parsed = None

    result["exit_code"] = proc.returncode
    result["stderr_tail"] = (proc.stderr or "")[-2000:]
    result["stdout_tail"] = (proc.stdout or "")[-4000:]

    if parsed is None:
        result["status"] = "runner_error"
        result["tests"] = []
        result["coverage"] = {}
        return result

    result["status"] = "pass" if parsed.get("status") == "pass" else "fail"
    result["tests"] = parsed.get("tests", [])
    result["coverage"] = parsed.get("coverage", {})
    result["build_errors"] = parsed.get("build_errors", [])
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    return result


def _discover_prompts(prompts_dir: Path, prompt: list[str] | None,
                      start: int | None, end: int | None) -> list[Path]:
    out = []
    for path in sorted(prompts_dir.glob("prompt_*.txt")):
        ident = parse_prompt_ident(path)
        if ident is None:
            continue
        if prompt is not None and ident not in prompt:
            continue
        n = parse_prompt_number(path)
        if prompt is None and (start is not None or end is not None):
            if n is None:
                continue
            if start is not None and n < start:
                continue
            if end is not None and n > end:
                continue
        out.append(path)
    return out


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompts", type=Path, default=Path("prompts"))
    parser.add_argument("--generated", type=Path, default=Path("generated"))
    parser.add_argument("--runs", type=Path, default=Path("behavior_runs"))
    parser.add_argument("--prompt", action="append", help="Run one prompt id (number or name, repeatable)")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--use-cached-spec", action="store_true")
    parser.add_argument("--design-based", action="store_true",
                        help="Reconstruct the produced design, gate it for conformity "
                             "with the prompt, and use it as the test spec.")
    parser.add_argument("--verbose", action="store_true")
    argv = parser.parse_args(args)

    prompts_dir = argv.prompts.resolve()
    generated_root = argv.generated.resolve()
    runs_dir = argv.runs.resolve()

    if argv.all:
        prompt_list = None
        start = end = None
    elif argv.prompt:
        prompt_list = argv.prompt
        start = end = None
    else:
        prompt_list = None
        start, end = argv.start, argv.end

    prompts = _discover_prompts(prompts_dir, prompt_list, start, end)
    if not prompts:
        print("No prompts found in %s" % prompts_dir)
        return 1

    runs_dir.mkdir(parents=True, exist_ok=True)

    all_results = []
    total_pass = 0
    total_pass_uncovered = 0
    total_fail = 0
    total_no_output = 0
    total_oracle_failed = 0
    total_conformity_failed = 0

    print("=" * 64)
    print("Behavioral tests: %d prompt(s)" % len(prompts))
    print("Prompts:  %s" % prompts_dir)
    print("Generated:%s" % generated_root)
    print("Runs:     %s" % runs_dir)
    print("=" * 64)

    for index, prompt_path in enumerate(prompts, 1):
        ident = parse_prompt_ident(prompt_path)
        run_dir = runs_dir / ident
        print("\n[%d/%d] Prompt %s" % (index, len(prompts), ident), flush=True)
        result = run_single(
            prompt_path, generated_root, run_dir,
            use_cached_spec=argv.use_cached_spec, verbose=argv.verbose,
            use_design=argv.design_based,
        )
        all_results.append(result)
        status = result.get("status")
        n_tests = len(result.get("tests", []))
        n_fail = sum(1 for t in result.get("tests", []) if t.get("status") != "pass")
        blc = result.get("business_logic_coverage", "full")
        if status == "pass":
            total_pass += 1
            if blc == "full":
                label = "PASS"
            else:
                label = "PASS \u26a0 uncovered"
                total_pass_uncovered += 1
        elif status == "fail":
            total_fail += 1
            label = "FAIL"
        elif status == "no_generated_output":
            total_no_output += 1
            label = "NO OUTPUT"
        elif status == "conformity_failed":
            total_conformity_failed += 1
            label = "CONFORMITY FAIL"
        else:
            total_oracle_failed += 1
            label = "ORACLE FAIL"
        print(
            "  status=%s tests=%d failed=%d" % (label, n_tests, n_fail),
            flush=True,
        )

    summary = {
        "started_at": all_results[0].get("started_at") if all_results else None,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "prompts_dir": str(prompts_dir),
        "generated_root": str(generated_root),
        "total": len(all_results),
        "pass": total_pass,
        "pass_uncovered": total_pass_uncovered,
        "fail": total_fail,
        "no_generated_output": total_no_output,
        "oracle_failed": total_oracle_failed,
        "conformity_failed": total_conformity_failed,
        "results": all_results,
    }
    summary_file = runs_dir / "summary.json"
    summary_file.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print("Pass:               %d" % total_pass)
    print("  of which uncovered:%d" % total_pass_uncovered)
    print("Fail:               %d" % total_fail)
    print("No output:          %d" % total_no_output)
    print("Oracle fail:        %d" % total_oracle_failed)
    print("Conformity fail:    %d" % total_conformity_failed)
    print("Summary: %s" % summary_file)

    return 0 if total_fail == 0 and total_oracle_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
