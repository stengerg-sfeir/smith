"""Execute a facade test plan in a subprocess and evaluate the outcome.

This is the FOURTH (final) stage of the facade tester. It takes a test plan
from ``facade_mapping.build_test_plan`` (an invocation string + expectation)
and runs it against the generated project in a subprocess, capturing exit code
and stdout, then checks the expectation.

It also handles SEEDING: plans are annotated by the mapper with ``creates``
(the entity a command creates) and ``refs`` (options that reference a parent
entity that must exist first). The executor
  1. topologically orders plans so creators run before their consumers,
  2. substitutes the real id of a freshly-created parent into the consumer's
     reference option,
  3. predicts ids from a fresh SQLite DB (autoincrement starts at 1).
This turns the earlier "FK parent missing" failures into real passing tests.
"""

from __future__ import annotations

import copy
import re
import shlex
import subprocess
import sys
from collections import deque
from pathlib import Path

from behavior_tests.fixtures import materialize_fixtures


def run_cli(invocation: str, cwd: Path, timeout: int = 30) -> dict:
    """Run a CLI invocation string in ``cwd`` and capture the result."""
    tokens = shlex.split(invocation)
    if not tokens or tokens[0] in ("python3", "python"):
        cmd = [sys.executable] + tokens[1:]
    else:
        cmd = tokens
    try:
        proc = subprocess.run(
            cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError as exc:
        return {"exit_code": -1, "stdout": "", "stderr": "no such file: %s" % exc}
    return {"exit_code": proc.returncode, "stdout": proc.stdout or "",
            "stderr": proc.stderr or ""}


def evaluate_plan(plan: dict, result: dict) -> tuple[bool, str]:
    """Check a mapped plan's smoke expectation against an execution result."""
    exp = plan.get("expected") or {}
    exp_code = exp.get("exit_code")
    if isinstance(exp_code, int) and result["exit_code"] != exp_code:
        return False, "exit_code=%d, expected %d" % (result["exit_code"], exp_code)
    if exp_code == "!=0" and result["exit_code"] == 0:
        return False, "exit_code=0, expected non-zero"
    if exp.get("stdout_nonempty") and not result["stdout"].strip():
        return False, "stdout is empty, expected non-empty"
    return True, "ok"


def execute_plan(plan: dict, project_dir: Path) -> dict:
    """Run one plan and return ``{intent_id, command, status, reason, ...}``."""
    result = run_cli(plan.get("invocation", ""), project_dir)
    ok, reason = evaluate_plan(plan, result)
    return {
        "intent_id": plan.get("intent_id", "?"),
        "command": plan.get("command", ""),
        "invocation": plan.get("invocation", ""),
        "status": "pass" if ok else "fail",
        "reason": reason,
        "exit_code": result["exit_code"],
        "stdout_tail": result["stdout"][-800:],
        "stderr_tail": result["stderr"][-800:],
    }


def start_fresh_project(project_dir: Path) -> None:
    """Remove generated SQLite DBs in the project dir so a run is reproducible."""
    for p in project_dir.glob("*.db"):
        try:
            p.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Seeding / dependency ordering
# ---------------------------------------------------------------------------

def _entity_provides(plan: dict) -> str:
    return plan.get("creates") or ""


def _entity_refs(plan: dict) -> list[tuple[str, str]]:
    out = []
    for r in plan.get("refs", []):
        if isinstance(r, dict) and r.get("flag") and r.get("entity"):
            out.append((r["flag"], r["entity"]))
    return out


def _is_delete(plan: dict) -> bool:
    return (plan.get("target") or "").lower().startswith("delete_")


def _topo_sort(plans: list[dict]) -> list[int]:
    """Order plan indices: creators, then readers/mutators, then deleters.

    - Creators (``creates != ""``) run first, ordered among themselves by FK
      reference (a creator that references a parent runs after that parent's
      creator).
    - Non-create, non-delete commands (update/list/report/restock/get) run next,
      so they see the seeded rows.
    - Deleters (``delete_*``) run LAST, so they never destroy a seeded row
      before another command uses it — and child deletes before a parent delete
      that FK references them.
    """
    n = len(plans)
    providers = [i for i in range(n) if _entity_provides(plans[i])]
    deleters = [i for i in range(n) if not _entity_provides(plans[i]) and _is_delete(plans[i])]
    others = [i for i in range(n) if not _entity_provides(plans[i]) and not _is_delete(plans[i])]

    provides: dict[str, int] = {}
    for i in providers:
        e = _entity_provides(plans[i])
        provides.setdefault(e, i)
    deps: list[list[int]] = [[] for _ in range(n)]
    indeg = [0] * n
    for i in providers:
        for _flag, ent in _entity_refs(plans[i]):
            j = provides.get(ent)
            if j is not None and j != i:
                deps[j].append(i)
                indeg[i] += 1
    q = deque(i for i in providers if indeg[i] == 0)
    order: list[int] = []
    while q:
        i = q.popleft()
        order.append(i)
        for j in deps[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)
    done = set(order)
    order.extend(i for i in providers if i not in done)  # creator cycles/leftovers last
    order.extend(others)
    order.extend(deleters)
    return order


def _rebuild_invocation(plan: dict) -> None:
    """Recompute the invocation string from the plan's args."""
    parts = ["python3"]
    if plan.get("entry"):
        parts.append(plan["entry"])
    if plan.get("kind") == "click_group" and plan.get("command"):
        parts.append(plan["command"])
    parts.extend(plan.get("positional_args", []))
    for pair in plan.get("option_args", []):
        parts.extend(pair)
    plan["invocation"] = " ".join(
        shlex.quote(p) if re.search(r"[\s'\"]", p) else p for p in parts
    )


def _substitute_refs(plan: dict, entity_provided: dict) -> None:
    """Replace an FK reference option value with a freshly created parent's id."""
    if not entity_provided:
        return
    changed = False
    for ref in plan.get("refs", []):
        flag = ref.get("flag", "")
        ent = ref.get("entity", "")
        if not flag or ent not in entity_provided:
            continue
        eid = str(entity_provided[ent])
        found = False
        for pair in plan["option_args"]:
            if pair and pair[0] == flag:
                if len(pair) == 1:
                    pair.append(eid)
                else:
                    pair[1] = eid
                found = True
                break
        if not found:
            plan["option_args"].append([flag, eid])
        changed = True
    if changed:
        _rebuild_invocation(plan)


def _substitute_fixtures(plan: dict, fx_paths: dict[str, Path]) -> None:
    """Materialised fixture paths substituted into the plan's invocation.

    Each plan carries ``fixtures: [{id, arg}]`` where ``arg`` is the command's
    positional argument name (e.g. ``input_file``) or an option ``--flag``
    whose value should become the fixture file path. We replace the placeholder
    value (whatever the LLM put there) with the real absolute path.
    """
    if not fx_paths:
        return
    changed = False
    dest_pos = {d: idx for idx, d in enumerate(plan.get("positional_dests", []))}
    for fx in plan.get("fixtures", []):
        fid = fx.get("id", "")
        arg = fx.get("arg", "")
        path = fx_paths.get(fid)
        if path is None:
            continue
        target = str(path.resolve())
        if arg.startswith("--"):
            for pair in plan["option_args"]:
                if pair and pair[0] == arg:
                    if len(pair) == 1:
                        pair.append(target)
                    else:
                        pair[1] = target
                    changed = True
                    break
            continue
        if arg in dest_pos:
            idx = dest_pos[arg]
            if 0 <= idx < len(plan["positional_args"]):
                plan["positional_args"][idx] = target
                changed = True
            continue
        # Fallback: first positional (or option) whose name hints at a file.
        idx = next((i for i, d in enumerate(plan.get("positional_dests", []))
                    if "file" in d or "path" in d or "input" in d or "csv" in d),
                   None)
        if idx is not None and 0 <= idx < len(plan["positional_args"]):
            plan["positional_args"][idx] = target
            changed = True
            continue
        pair = next((p for p in plan.get("option_args", [])
                     if p and any(k in p[0].lstrip("-") for k in
                                  ("file", "path", "input", "csv"))), None)
        if pair is not None:
            if len(pair) == 1:
                pair.append(target)
            else:
                pair[1] = target
            changed = True
    if changed:
        _rebuild_invocation(plan)


def _materialise_plans_fixtures(plans: list[dict], fixtures: dict | None,
                                out_dir: Path) -> dict[str, Path]:
    """Materialise every fixture referenced by the plans once, return id->path."""
    used: list[str] = []
    for plan in plans:
        for fx in plan.get("fixtures", []):
            if isinstance(fx, dict) and fx.get("id") and fx["id"] not in used:
                used.append(fx["id"])
    return materialize_fixtures(fixtures, used, out_dir)


def execute_prompt(plans: list[dict], project_dir: Path,
                   fresh_db: bool = True,
                   fixtures: dict | None = None,
                   fixtures_out_dir: Path | None = None) -> dict:
    """Execute all plans for one prompt with seeding and aggregate outcomes.

    Orders creators before consumers, substitutes freshly-seeded parent ids into
    reference options, and predicts ids from a fresh SQLite DB. Plans that run
    but aren't expected to create (list/report/delete) run in order after their
    dependencies.

    ``fixtures`` is the fixture library (id -> fixture). Need-indicator plans
    reference ``fixtures: [{id, arg}]``; before execution we materialise those
    fixtures to ``fixtures_out_dir`` (default ``<cwd>/behavior_runs/facade/
    fixtures``) and substitute the resulting file paths into the invocation.
    """
    if fresh_db:
        start_fresh_project(project_dir)
    working = [copy.deepcopy(p) for p in plans]
    if fixtures:
        out = fixtures_out_dir or Path("behavior_runs/facade/fixtures")
        fx_paths = _materialise_plans_fixtures(working, fixtures, out)
    else:
        fx_paths = {}
    order = _topo_sort(working)
    entity_provided: dict[str, int] = {}
    entity_counts: dict[str, int] = {}
    results = []
    for i in order:
        plan = working[i]
        _substitute_refs(plan, entity_provided)
        _substitute_fixtures(plan, fx_paths)
        res = execute_plan(plan, project_dir)
        created = _entity_provides(plan)
        if created and res["status"] == "pass":
            entity_counts[created] = entity_counts.get(created, 0) + 1
            entity_provided[created] = entity_counts[created]
        results.append(res)
    n_pass = sum(1 for r in results if r["status"] == "pass")
    return {
        "total": len(results),
        "pass": n_pass,
        "fail": len(results) - n_pass,
        "results": results,
    }
