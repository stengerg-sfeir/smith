"""Mutation harness for the semantic oracle (stage 4 validation).

An oracle that always passes is worthless. This harness proves each invariant
is LOAD-BEARING: it takes the generated snapshot, injects a bug that MUST
break a specific invariant, re-runs the SAME oracle on the mutated copy, and
requires the invariant to fail.

  * ``get_by_id_dict``  every repository ``get_by_id`` returns a plain dict
    instead of an entity instance. If the DESIGN-derived round-trip and
    listing invariants still pass, they are not observing types.
  * ``stub:<method>``  replaces the body of the service method an invariant
    targets with ``return None``. If the invariant still passes, it is not
    actually observing that method's behaviour.

Mutations are derived from the oracle's own invariant list, never from the
implementation, so a mutation cannot have been "known" to the code.

Usage:
    python3 -m behavior_tests.mutate_semantic --project library_system
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# invariant id -> the service method(s) it observes (first match wins).
_MUTATION_TARGETS = {
    "library_system": {
        "borrow then return restores available_copies": ["return_book"],
        "return_book accepts an overdue loan": ["return_book"],
        "get_overdue_loans returns overdue LOANS": ["get_overdue_loans"],
        "renew_membership toggles is_active": ["renew_membership"],
        "member history surfaces the member's loans": [
            "get_member_history", "member_history", "history"],
        "search_books finds a book by its title": ["search_books", "search_book"],
        "search_books finds a book by its author's name": [
            "search_books", "search_book"],
    },
    "expenses": {
        "get_monthly_report filters by month": ["get_monthly_report"],
        "get_monthly_report returns the spec's three pieces": [
            "get_monthly_report"],
        "budget status compares the month, not lifetime spending": [
            "get_monthly_report"],
        "get_yearly_summary exposes monthly totals": ["get_yearly_summary"],
        "get_yearly_summary returns top categories and the average": [
            "get_yearly_summary"],
        "get_category_spending reports a total": ["get_category_spending"],
        "get_category_spending keys its aggregate as 'total'": [
            "get_category_spending"],
        "budget status reflects actual spending": [
            "check_category_budget_status", "check_budget_status", "check_budget"],
        "repository budget status compares the limit to spending": [
            "check_budget_status"],
        "detect_recurring marks recurring rows": ["detect_recurring"],
    },
}


def _stub_method(source, method_names):
    """Replace EVERY matching method's body with ``return None``.

    EVERY match, not just the first. A mutation that leaves one of several
    alternative methods intact proves nothing: library_system's history
    listing is reachable as ``get_member_history`` AND ``history``, and
    stubbing only the first name found left the invariant passing on the
    untouched one — scored as a false "survived", which hides a real oracle
    weakness. Returns None when NOTHING matched, so an inapplicable mutation
    is reported as such instead of as a survival.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    hits = 0
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in method_names:
            continue
        node.body = [ast.Return(value=ast.Constant(value=None))]
        hits += 1
    if not hits:
        return None
    try:
        return ast.unparse(tree)
    except Exception:  # noqa: BLE001
        return None


def _mutate_stub(snapshot, method_names):
    """Stub the targets wherever they live, service OR repository.

    The oracle legitimately observes a repository method when that is where
    the specification puts the rule (expenses' "check if a category has
    exceeded its budget" is ``category_repository.
    check_category_budget_status``). Scanning only ``*_service.py`` left that
    method untouched, so the invariant passed on the unmutated code and was
    scored as a false survival.
    """
    applied = False
    for path in sorted(snapshot.glob("*.py")):
        new = _stub_method(path.read_text(encoding="utf-8"), method_names)
        if new is not None:
            path.write_text(new, encoding="utf-8")
            applied = True
    return applied


def _mutate_get_by_id_dict(snapshot):
    """Make repo ``get_by_id`` return a dict instead of the entity instance."""
    applied = False
    for path in sorted(snapshot.glob("*_repository.py")):
        text = path.read_text(encoding="utf-8")
        if "def get_by_id" not in text:
            continue
        lines = text.split("\n")
        out, inside = [], False
        for line in lines:
            if line.lstrip().startswith("def get_by_id("):
                inside = True
                out.append(line)
                continue
            if inside and line.strip().startswith("return ") and "(" in line:
                indent = line[: len(line) - len(line.lstrip())]
                out.append(indent + "return dict(row) if row else None")
                applied = True
                inside = False
                continue
            out.append(line)
        if applied:
            path.write_text("\n".join(out), encoding="utf-8")
    return applied


# The invariant that must be the one to fail when a LIKE search stops
# covering the FK-referenced entity's text — the S17 defect shape.
_JOIN_SEARCH_INVARIANT = {
    "library_system": "search_books finds a book by its author's name",
}

_BASE_JOIN = re.compile(r"FROM (\w+) LEFT JOIN (\w+)")
_LIKE_TERM = re.compile(r"(\w+)\.(\w+) LIKE \?")


def _mutate_search_ignores_join(snapshot):
    """Rewrite a JOINed LIKE search to LIKE the entity's OWN column instead.

    Reproduces S17 without changing the bind count (every ``?`` keeps a
    value), so the search still runs and still matches the entity's own text:
    only the FK-referenced neighbour's coverage is lost. If the author-by-name
    invariant survives this, it is not observing the join at all.
    """
    applied = False
    for path in sorted(snapshot.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        if "LEFT JOIN" not in text or "LIKE ?" not in text:
            continue
        m = _BASE_JOIN.search(text)
        if not m:
            continue
        base, other = m.group(1), m.group(2)
        own = next(
            (lm.group(2) for lm in _LIKE_TERM.finditer(text)
             if lm.group(1) == base),
            None,
        )
        if own is None:
            continue
        new = _LIKE_TERM.sub(
            lambda lm: ("%s.%s LIKE ?" % (base, own))
            if lm.group(1) == other else lm.group(0),
            text,
        )
        if new != text:
            path.write_text(new, encoding="utf-8")
            applied = True
    return applied


def _run_oracle(root, project):
    out = Path(tempfile.mktemp(suffix=".json"))
    proc = subprocess.run(
        [
            sys.executable, "-m", "behavior_tests.semantic_oracle",
            "--project", project, "--generated", str(root), "--json", str(out),
        ],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    if not out.exists():
        return {"status": "error", "stderr": proc.stderr[-500:]}
    try:
        return json.loads(out.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def mutate(project, generated_root, verbose=True):
    src = generated_root / project
    if not src.is_dir():
        raise SystemExit("no generated output at %s" % src)

    base = _run_oracle(generated_root, project)
    result = {
        "project": project,
        "baseline_status": (base or {}).get("status"),
        "baseline_passed": (base or {}).get("passed"),
        "baseline_total": (base or {}).get("total"),
        "mutants": [],
    }
    if (base or {}).get("status") != "pass":
        result["status"] = "baseline_failed"
        result["baseline_tests"] = [
            t for t in (base or {}).get("tests", []) if t["status"] != "pass"
        ]
        if verbose:
            for t in result["baseline_tests"]:
                print("  baseline FAIL %s -> %s" % (t["id"], t.get("detail")))
        return result

    work = Path(tempfile.mkdtemp(prefix="oracle_mut_"))
    try:
        design_root = work / "design"
        design_root.mkdir(parents=True)
        shutil.copytree(src, design_root / project)
        if _mutate_get_by_id_dict(design_root / project):
            res = _run_oracle(design_root, project)
            failed = [t["id"] for t in (res or {}).get("tests", [])
                      if t["status"] != "pass"]
            design_ids = [
                t["id"] for t in (base or {}).get("tests", [])
                if t["family"] == "design"
            ]
            caught = [i for i in failed if i in design_ids]
            result["mutants"].append({
                "id": "get_by_id_dict",
                "label": "repositories return dicts instead of entities",
                "status": "killed" if caught else "survived",
                "failing_tests": caught,
            })

        want_join = _JOIN_SEARCH_INVARIANT.get(project)
        if want_join:
            root = work / ("m%d" % len(result["mutants"]))
            root.mkdir(parents=True)
            shutil.copytree(src, root / project)
            if _mutate_search_ignores_join(root / project):
                res = _run_oracle(root, project)
                failed = [t["id"] for t in (res or {}).get("tests", [])
                          if t["status"] != "pass"]
                result["mutants"].append({
                    "id": "search_ignores_join",
                    "label": "LIKE search drops the JOINed entity's columns",
                    "status": "killed" if want_join in failed else "survived",
                    "failing_tests": failed,
                })

        targets = _MUTATION_TARGETS.get(project, {})
        for inv in (base or {}).get("tests", []):
            if inv["family"] != "spec":
                continue
            methods = targets.get(inv["id"])
            if not methods:
                result["mutants"].append({
                    "id": inv["id"], "label": "no mutation target",
                    "status": "inapplicable",
                })
                continue
            root = work / ("m%d" % len(result["mutants"]))
            root.mkdir(parents=True)
            shutil.copytree(src, root / project)
            if not _mutate_stub(root / project, methods):
                result["mutants"].append({
                    "id": inv["id"], "label": "stub %s" % methods,
                    "status": "inapplicable",
                })
                continue
            res = _run_oracle(root, project)
            failed = [t["id"] for t in (res or {}).get("tests", [])
                      if t["status"] != "pass"]
            result["mutants"].append({
                "id": inv["id"],
                "label": "stubbed %s" % ", ".join(methods),
                "status": "killed" if inv["id"] in failed else "survived",
                "failing_tests": failed,
            })
    finally:
        shutil.rmtree(work, ignore_errors=True)

    survivors = [m for m in result["mutants"] if m["status"] == "survived"]
    result["status"] = "pass" if not survivors else "fail"
    if verbose:
        for m in result["mutants"]:
            print("  %-8s %-46s %s" % (
                m["status"], m["id"], m.get("label", "")))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--generated", type=Path, default=Path("generated"))
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)

    res = mutate(args.project, args.generated)
    print("%s mutation: %s (baseline %s/%s)" % (
        res["project"], res["status"],
        res.get("baseline_passed"), res.get("baseline_total")))
    if args.json:
        args.json.write_text(
            json.dumps(res, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return 0 if res["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
