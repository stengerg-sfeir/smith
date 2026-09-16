#!/usr/bin/env python3
"""Baseline: what Claude Code produces for the same specifications.

Runs `claude -p` (non-interactive) once per named prompt with the prompt file
VERBATIM, materialises whatever it writes into a working directory, then
subjects that directory to the *same* gates the generator is held to:
`agentlib.bench.named_prompt_suite.functional_failures` and
`conformity_failures`, plus a compile check.

Two things this harness is deliberately honest about:

* No prompt file names an entry-point FILE (`cli.py` appears nowhere in
  `prompts/`), yet the gate suite invokes `python cli.py <args>` by
  construction. So an entry point is detected in Claude's output and, when it
  is not literally `cli.py`, a thin dispatch shim is written — and the result
  is reported as `raw` and `with entry-point shim` SEPARATELY. Conflating the
  two would measure filename coincidence rather than specification
  conformance.
* There is no generator log for a Claude run, so the marker check has no
  analogue. A labelled proxy is used instead: stub markers left in the
  produced source.

Usage:
    python3 bench.py claude --only hello_world
    python3 bench.py claude                  # all six named prompts
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

# The repository root: this module lives in agentlib/bench/, so the root is
# three levels up (agentlib/bench -> agentlib -> root).
ROOT = Path(__file__).resolve().parent.parent.parent
PROMPTS_DIR = ROOT / "prompts"
WORK_ROOT = Path("/tmp/claude_baseline")
BASELINE_DIR = ROOT / "baseline"
CLAUDE_TIMEOUT = 3600

TAIL = (
    "\n\n---\n\nImplement this completely in the current working directory, as "
    "Python files written directly here. Do not ask for confirmation or for "
    "more information: produce the full, runnable implementation now."
)

# Proxy for the generator's marker log: a Claude run has no pipeline log, so
# the nearest observable is a stub left behind in the shipped source. A bare
# word match is wrong here — an enum member `TaskStatus.TODO` and a
# `print("TODO tasks:")` are legitimate code, not stubs — so the markers must
# appear as COMMENT tags.
_STUB_MARKERS = re.compile(
    r"NotImplementedError|(?:#|//)\s*(?:TODO|FIXME|XXX)\b"
)

SHIM_TEMPLATE = (
    '"""Test-harness shim: dispatch to the entry point Claude chose.\n\n'
    "No prompt names a CLI entry file; the gate suite invokes `cli.py`. This\n"
    "shim exists only so those gates can run, and is not Claude's output.\n"
    '"""\n'
    "import sys\n\nfrom %s import %s\n\n\n"
    'if __name__ == "__main__":\n    sys.exit(%s())\n'
)


def _clean_env() -> dict:
    """Environment for the child `claude`, without the IDE bridge variables.

    `CLAUDE_CODE_SSE_PORT` makes a child Claude attach to the editor's bridge;
    the baseline must be a plain headless run.
    """
    return {
        key: value for key, value in os.environ.items()
        if not key.startswith("CLAUDE_CODE") and key != "CLAUDECODE"
    }


def _run_claude(ident: str, workdir: Path, model: str | None) -> dict:
    """One non-interactive Claude Code run, timed."""
    prompt_text = (PROMPTS_DIR / ("prompt_%s.txt" % ident)).read_text(
        encoding="utf-8")
    argv = [
        "claude", "-p", prompt_text + TAIL,
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
        "--no-session-persistence",
    ]
    if model:
        argv += ["--model", model]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv, cwd=str(workdir), capture_output=True, text=True,
            timeout=CLAUDE_TIMEOUT, stdin=subprocess.DEVNULL,
            env=_clean_env(),
        )
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        exit_code, stdout, stderr = -1, "", "timeout after %ds" % CLAUDE_TIMEOUT
    elapsed = time.monotonic() - started

    payload = {}
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        pass
    return {
        "elapsed_s": round(elapsed, 1),
        "exit": exit_code,
        "claude_duration_ms": payload.get("duration_ms"),
        "claude_cost_usd": payload.get("total_cost_usd"),
        "claude_turns": payload.get("num_turns"),
        "claude_model": _model_of(payload),
        "claude_result_tail": (payload.get("result") or stderr or "")[-300:],
    }


def _model_of(payload: dict) -> str:
    usage = payload.get("modelUsage") or {}
    if isinstance(usage, dict) and usage:
        return ", ".join(sorted(usage))
    return payload.get("model") or "?"


def _required_entry(ident: str) -> str:
    """The entry file the gate suite invokes, by construction."""
    if ident == "hello_world":
        return "hello.py"
    if ident == "cli_tool":
        return "csv_to_json.py"
    return "cli.py"


def _python_files(project: Path) -> list[Path]:
    return sorted(p for p in project.rglob("*.py") if "__pycache__" not in p.parts)


def _stub_markers(project: Path) -> list[str]:
    hits = []
    for path in _python_files(project):
        for number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if _STUB_MARKERS.search(line):
                hits.append("%s:%d %s" % (path.name, number, line.strip()[:80]))
    return hits


def _module_path(project: Path, path: Path) -> str:
    """The dotted import path of ``path`` as seen from the project root.

    A nested PACKAGE (``expense_tracker/cli.py``) must be imported as
    ``expense_tracker.cli``. Using the bare stem produced a shim containing
    ``from cli import cli`` inside a root ``cli.py`` — importing ITSELF — so
    every command of that project failed on an ImportError that had nothing to
    do with the code being measured.
    """
    parts = list(path.relative_to(project).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _click_command_names(path: Path) -> list[str]:
    """Top-level functions decorated ``@<obj>.group()`` / ``.command()``.

    Parsed, not pattern-matched. A multi-line ``@click.option(...)`` block sits
    between the group decorator and the ``def``, and a line-based regex that
    only skipped single-line decorators never reached the function — so a
    correct click CLI in a package was reported as having no entry point at
    all, and the harness silently measured an unpatched tree.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    names = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            target = decorator.func
            if isinstance(target, ast.Attribute) and target.attr in (
                "group", "command"
            ):
                names.append(node.name)
                break
            if isinstance(target, ast.Name) and target.id in ("group", "command"):
                names.append(node.name)
                break
    return names


def _detect_click_entry(project: Path) -> tuple[str, str] | None:
    """(dotted module path, callable name) of the CLI Claude wrote, if any."""
    candidates = []
    for path in _python_files(project):
        for name in _click_command_names(path):
            candidates.append((_module_path(project, path), name))
    if not candidates:
        return None
    preferred = ("cli", "main", "app", "commands", "__main__")
    for module, name in candidates:
        if module.split(".")[-1] in preferred:
            return module, name
    return candidates[0]


def _detect_script_entry(project: Path) -> str | None:
    for path in _python_files(project):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "__main__" in text:
            return path.name
    return None


def _install_shim(project: Path, required: str, ident: str) -> str:
    """Create the entry file the gates expect; returns what was done."""
    target = project / required
    if target.exists():
        return "none needed (already present)"
    if ident in ("hello_world", "cli_tool"):
        real = _detect_script_entry(project)
        if real is None:
            return "no candidate entry point found"
        target.write_text(
            '"""Test-harness shim: run the script Claude chose."""\n'
            "import runpy\n\n"
            'runpy.run_path("%s", run_name="__main__")\n' % real,
            encoding="utf-8",
        )
        return "runpy -> %s" % real
    found = _detect_click_entry(project)
    if found is None:
        return "no click command found"
    module, name = found
    target.write_text(
        SHIM_TEMPLATE % (module, name, name), encoding="utf-8")
    return "dispatch %s.%s" % (module, name)


def _compile_failures(project: Path) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(project)],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return []
    return ["compileall -> exit=%d %s"
            % (proc.returncode, (proc.stderr or "").strip()[-200:])]


def _gates(ident: str, project: Path) -> dict:
    from agentlib.bench.named_prompt_suite import (
        conformity_failures,
        functional_failures,
    )

    functional, metrics = functional_failures(ident, project)
    return {
        "functional": functional,
        "conformity": conformity_failures(ident, project),
        "metrics": metrics,
    }


def _profile(ident: str, model: str | None, destination_root: Path,
             reuse: bool = False) -> dict:
    workdir = WORK_ROOT / ident
    shutil.rmtree(workdir, ignore_errors=True)
    source = destination_root / ident

    record: dict = {"ident": ident, "required_entry": _required_entry(ident)}
    timing_path = destination_root / ("%s.timing.json" % ident)
    if reuse:
        if not source.is_dir():
            raise SystemExit("nothing to reuse for %s at %s" % (ident, source))
        shutil.copytree(source, workdir)
        # A reuse run measures the GATES, not the generation: recover the
        # timing of the run that produced this output instead of showing
        # "reused", so the report keeps the measurement it exists to check.
        record.update({
            "elapsed_s": "reused", "exit": "-", "claude_duration_ms": None,
            "claude_cost_usd": None, "claude_turns": None,
            "claude_model": "reused", "claude_result_tail": "",
        })
        if timing_path.is_file():
            try:
                record.update(json.loads(timing_path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                pass
    else:
        workdir.mkdir(parents=True)
        record.update(_run_claude(ident, workdir, model))
        timing_path.write_text(json.dumps({
            key: record[key] for key in (
                "elapsed_s", "exit", "claude_duration_ms", "claude_cost_usd",
                "claude_turns", "claude_model",
            )
        }, indent=2), encoding="utf-8")

    record["files"] = [
        p.relative_to(workdir).as_posix() for p in _python_files(workdir)
    ]
    record["stub_markers"] = _stub_markers(workdir)
    record["entry_raw_present"] = (workdir / record["required_entry"]).is_file()
    record["compile"] = _compile_failures(workdir)
    record["raw"] = (
        _gates(ident, workdir) if record["entry_raw_present"] else None
    )

    # Persist the SOURCE BEFORE the shim: the gates must be re-runnable
    # (`--reuse`) against the same untouched output, and a persisted shim would
    # otherwise read as "Claude named the entry file cli.py".
    destination = destination_root / ident
    shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(
        workdir, destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.db"),
    )

    record["entry_note"] = _install_shim(
        workdir, record["required_entry"], ident)
    record["shimmed"] = _gates(ident, workdir)
    return record


def _verdict(failures) -> str:
    if failures is None:
        return "n/a (entry file absent)"
    return "PASS" if not failures else "FAIL (%d)" % len(failures)


def _render_report(records: list[dict]) -> str:
    lines = [
        "# Claude Code baseline — the same six specifications",
        "",
        "Each prompt file was passed **verbatim** to `claude -p` (non-interactive",
        "Claude Code), in an empty directory, with one imperative tail asking for",
        "the full runnable implementation. The output is then subjected to the",
        "SAME gates as the generator: `functional_failures` and",
        "`conformity_failures` from `agentlib.bench.named_prompt_suite`.",
        "",
        "**No prompt names an entry-point file**, yet the gates invoke",
        "`python cli.py ...` (and `hello.py` / `csv_to_json.py`) by construction.",
        "Columns are therefore split: *raw* = gates against Claude's untouched",
        "output; *shim* = gates after a thin dispatch `cli.py` (or runpy shim) was",
        "added purely so the gates can run.",
        "",
        "| prompt | wall (s) | turns | sortie | fichiers | entrée | raw fonctionnel | raw conforme | shim fonctionnel | shim conforme |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rec in records:
        raw = rec["raw"] or {}
        shim = rec["shimmed"] or {}
        lines.append(
            "| `%s` | %s | %s | %s | %d | %s | %s | %s | %s | %s |"
            % (
                rec["ident"], rec["elapsed_s"], rec["claude_turns"] or "?",
                rec["exit"], len(rec["files"]),
                (rec["required_entry"] if rec["entry_raw_present"] else "absent"),
                _verdict(raw.get("functional")), _verdict(raw.get("conformity")),
                _verdict(shim.get("functional")), _verdict(shim.get("conformity")),
            )
        )
    lines.append("")

    for rec in records:
        lines += [
            "## `%s`" % rec["ident"],
            "",
            "- durée murale : **%s s**" % rec["elapsed_s"],
            "- interne Claude : duration_ms=%s, tours=%s, coût=%s USD, modèle=%s"
            % (rec["claude_duration_ms"], rec["claude_turns"],
               rec["claude_cost_usd"], rec["claude_model"]),
            "- exit=%s" % rec["exit"],
            "- fichiers produits (%d) : %s"
            % (len(rec["files"]), ", ".join(rec["files"]) or "aucun"),
            "- entrée attendue par les portes : `%s` — %s"
            % (rec["required_entry"],
               "présente" if rec["entry_raw_present"] else "**absente**"),
            "- shim : %s" % rec["entry_note"],
            "- marqueurs de stub (proxy) : %s"
            % ("aucun" if not rec["stub_markers"]
               else "%d — %s" % (len(rec["stub_markers"]),
                                 "; ".join(rec["stub_markers"][:3]))),
            "- compile : %s" % ("OK" if not rec["compile"] else rec["compile"]),
        ]
        for label, key in (("raw", "raw"), ("avec shim", "shimmed")):
            data = rec.get(key)
            if data is None:
                lines.append("- **%s** : non applicable (fichier d'entrée absent)"
                             % label)
                continue
            lines.append("- **%s** fonctionnel : %s"
                         % (label, _verdict(data["functional"])))
            for failure in data["functional"][:5]:
                lines.append("    - %s" % failure)
            lines.append("- **%s** conformité : %s"
                         % (label, _verdict(data["conformity"])))
            for failure in data["conformity"][:5]:
                lines.append("    - %s" % failure)
        if rec["claude_result_tail"]:
            lines += ["", "```", rec["claude_result_tail"].strip(), "```"]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", default=None,
                        help="restrict to one prompt ident (repeatable)")
    parser.add_argument("--model", default=None,
                        help="Claude model alias; default = the CLI's own default")
    parser.add_argument("--label", default=None,
                        help="sub-directory and report suffix for this run")
    parser.add_argument("--reuse", action="store_true",
                        help="re-run the gates on the persisted output only")
    args = parser.parse_args(argv)

    from agentlib.bench.named_prompt_suite import NAMED_PROMPTS

    destination_root = (
        BASELINE_DIR if args.label is None else BASELINE_DIR / args.label
    )
    stem = (
        "claude_baseline_report" if args.label is None
        else "claude_baseline_report_%s" % args.label
    )
    # A reuse run may safely write the canonical report: the timing it cannot
    # measure is recovered from the ``<ident>.timing.json`` sidecar that the
    # run which produced the output wrote, so the measurement survives.
    report_name = "%s.md" % stem
    targets = args.only or list(NAMED_PROMPTS)
    destination_root.mkdir(parents=True, exist_ok=True)
    records = []
    for ident in targets:
        print("=== claude baseline: %s ===" % ident, flush=True)
        record = _profile(ident, args.model, destination_root, args.reuse)
        records.append(record)
        print("  wall=%ss exit=%s files=%d raw_func=%s shim_func=%s"
              % (record["elapsed_s"], record["exit"], len(record["files"]),
                 _verdict((record["raw"] or {}).get("functional")),
                 _verdict(record["shimmed"]["functional"])), flush=True)

    report = _render_report(records)
    (ROOT / "analysis" / report_name).write_text(report, encoding="utf-8")
    print("\nreport -> analysis/%s" % report_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
