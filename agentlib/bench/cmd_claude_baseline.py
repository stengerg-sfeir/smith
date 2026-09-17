#!/usr/bin/env python3
"""Baseline: what Claude Code produces for the same specifications.

Runs `claude -p` (non-interactive) once per named prompt with the prompt file
VERBATIM, materialises whatever it writes into a working directory, then
subjects that directory to the *same* gates the generator is held to:
`agentlib.bench.named_prompt_suite.functional_failures` and
`conformity_failures`, plus a compile check.

Three things this harness is deliberately honest about:

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
* **Consumption** is reported in the units each side can actually prove. The
  CLI's own JSON payload carries the token totals of the run (`usage`), so
  those are exact and per project; the source chars are read back off disk,
  which is the one unit directly comparable with the generator. Neither number
  is inferred from the other.

What is measured is KEPT: `<ident>.claude.json` holds the raw payload and
`<ident>.timing.json` the derived fields, so `--reuse` re-renders every metric
— including one added later — without paying for another run.

Usage:
    python3 bench.py claude --only hello_world
    python3 bench.py claude                  # all six named prompts
    python3 bench.py claude --reuse          # re-render from what was kept
"""
import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
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


def _run_claude(ident: str, workdir: Path,
                model: str | None) -> tuple[dict, dict]:
    """One non-interactive Claude Code run, timed.

    Returns `(measurement, raw_payload)`: the caller persists the payload so a
    later metric never requires re-running the model.
    """
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
    # The payload travels back with the summary: the caller persists it
    # verbatim, which is what keeps every later metric re-derivable without
    # paying for another run.
    return _measured_fields(payload, stderr, elapsed, exit_code), payload


def _model_of(payload: dict) -> str:
    usage = payload.get("modelUsage") or {}
    if isinstance(usage, dict) and usage:
        return ", ".join(sorted(usage))
    return payload.get("model") or "?"


# The token buckets a Claude run reports. `input` EXCLUDES everything cached:
# `cache_read` is the context re-read on every turn, and in an agentic loop
# that is where the traffic goes — dropping it would understate a run by an
# order of magnitude, so it keeps its own column.
_USAGE_KEYS = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cache_read", "cache_read_input_tokens"),
    ("cache_creation", "cache_creation_input_tokens"),
)


def _as_int(value) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _usage_of(payload: dict) -> dict:
    """Token totals of one run, as the CLI reported them.

    A run that never reached the API reports zeros; they are kept as zeros
    rather than blanked, so "the model emitted nothing" stays visible instead
    of looking like a missing column.
    """
    usage = payload.get("usage") or {}
    totals = {label: _as_int(usage.get(key)) for label, key in _USAGE_KEYS}
    totals["total"] = sum(totals.values())
    return totals


def _model_usage_of(payload: dict) -> dict:
    """Per-model tokens, tolerant of how the payload spells its keys.

    The per-model block is the only place a multi-model run (subagents) can be
    told apart, so it is kept whole instead of folded into the total.
    """
    out = {}
    for model, entry in (payload.get("modelUsage") or {}).items():
        if not isinstance(entry, dict):
            continue
        flat = {key.lower().replace("_", ""): value for key, value in entry.items()}
        out[model] = {
            "input": _as_int(flat.get("inputtokens")),
            "output": _as_int(flat.get("outputtokens")),
            "cache_read": _as_int(flat.get("cachereadinputtokens")),
            "cache_creation": _as_int(flat.get("cachecreationinputtokens")),
            "cost_usd": entry.get("costUSD", entry.get("cost_usd")),
        }
    return out


def _measured_fields(payload: dict, stderr: str, elapsed: float,
                     exit_code) -> dict:
    """The measurement of one run, every field taken from its own payload."""
    return {
        "elapsed_s": round(elapsed, 1),
        "exit": exit_code,
        "claude_duration_ms": payload.get("duration_ms"),
        "claude_api_ms": payload.get("duration_api_ms"),
        "claude_cost_usd": payload.get("total_cost_usd"),
        "claude_turns": payload.get("num_turns"),
        "claude_model": _model_of(payload),
        "claude_usage": _usage_of(payload),
        "claude_model_usage": _model_usage_of(payload),
        "claude_is_error": payload.get("is_error") is True,
        "claude_error": (
            payload.get("result") or "" if payload.get("is_error") else ""
        ),
        "claude_result_tail": (payload.get("result") or stderr or "")[-300:],
    }


def _read_json(path: Path):
    """Parsed JSON, or None: a missing or corrupt sidecar is not an error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _required_entry(ident: str) -> str:
    """The entry file the gate suite invokes, by construction."""
    if ident == "hello_world":
        return "hello.py"
    if ident == "cli_tool":
        return "csv_to_json.py"
    return "cli.py"


def _python_files(project: Path) -> list[Path]:
    return sorted(p for p in project.rglob("*.py") if "__pycache__" not in p.parts)


def _all_source_files(project: Path) -> list[Path]:
    """Every file the run shipped, minus caches and SQLite databases.

    Not the comparable unit: the generator's `_source_metrics` counts `**/*.py`
    and nothing else, so measuring Claude's README and requirements.txt here
    would credit it with prose the generator never writes. Reported alongside,
    never instead.
    """
    return sorted(
        path for path in project.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in (".pyc", ".db")
    )


def _chars_of(files: list[Path]) -> int:
    """Chars, not bytes: both sides compare text, and both decode as text."""
    return sum(
        len(path.read_text(encoding="utf-8", errors="replace"))
        for path in files
    )


def _source_chars(project: Path) -> tuple[int, int]:
    """`(files, chars)` of the PYTHON source — the generator's own unit.

    `cmd_cost_profile._source_metrics` measures `**/*.py` and their chars. A
    comparison of "source produced" is only a comparison if the same thing is
    counted on both sides; counting every file here would inflate Claude's side
    with markdown the generator never writes.
    """
    files = _python_files(project)
    return len(files), _chars_of(files)


def _source_chars_all(project: Path) -> tuple[int, int]:
    """`(files, chars)` of everything the run shipped, for context."""
    files = _all_source_files(project)
    return len(files), _chars_of(files)


def _prompt_chars(ident: str) -> int:
    """Chars actually sent to the model: the prompt file plus the tail."""
    return len(
        (PROMPTS_DIR / ("prompt_%s.txt" % ident)).read_text(encoding="utf-8")
    ) + len(TAIL)


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


# The derived measurement kept in `<ident>.timing.json`, as a tuple so a field
# added to `_measured_fields` cannot be silently dropped on the way to disk.
TIMING_KEYS = (
    "elapsed_s", "exit", "claude_duration_ms", "claude_api_ms",
    "claude_cost_usd", "claude_turns", "claude_model", "claude_usage",
    "claude_model_usage",
)


def _persist_run(destination_root: Path, ident: str, record: dict,
                 payload: dict) -> None:
    """Keep what was derived AND what the CLI actually said.

    The raw payload is written beside the timing because the report is rendered
    from it: a metric added later (tokens today, something else tomorrow) can
    then be re-derived with `--reuse` instead of a new billed run.
    """
    (destination_root / ("%s.claude.json" % ident)).write_text(
        json.dumps(payload, indent=2), encoding="utf-8")
    (destination_root / ("%s.timing.json" % ident)).write_text(
        json.dumps({key: record.get(key) for key in TIMING_KEYS}, indent=2),
        encoding="utf-8")


def _load_run(destination_root: Path, ident: str) -> dict:
    """The measurement of the run that produced the persisted output.

    The raw payload WINS where it speaks: the token totals are re-derived from
    it, so a corrected extractor re-renders an old run correctly. The timing
    sidecar stays authoritative for the wall clock, which no payload contains.
    Output kept by a run that predates the sidecars reports `reused` and no
    tokens, rather than inventing either.
    """
    timing = _read_json(destination_root / ("%s.timing.json" % ident)) or {}
    payload = _read_json(destination_root / ("%s.claude.json" % ident)) or {}
    measured = {
        "elapsed_s": timing.get("elapsed_s", "reused"),
        "exit": timing.get("exit", "-"),
        "claude_duration_ms": timing.get("claude_duration_ms"),
        "claude_api_ms": timing.get("claude_api_ms"),
        "claude_cost_usd": timing.get("claude_cost_usd"),
        "claude_turns": timing.get("claude_turns"),
        "claude_model": timing.get("claude_model", "reused"),
        "claude_usage": timing.get("claude_usage"),
        "claude_model_usage": timing.get("claude_model_usage") or {},
        "claude_result_tail": "",
    }
    if payload:
        measured["claude_usage"] = _usage_of(payload)
        measured["claude_model_usage"] = _model_usage_of(payload)
        if not timing:
            measured["claude_duration_ms"] = payload.get("duration_ms")
            measured["claude_api_ms"] = payload.get("duration_api_ms")
            measured["claude_cost_usd"] = payload.get("total_cost_usd")
            measured["claude_turns"] = payload.get("num_turns")
            measured["claude_model"] = _model_of(payload)
    return measured


def _refuse_failed_run(ident: str, measured: dict) -> None:
    """Abort on a run that measured nothing, BEFORE it can overwrite a baseline.

    A `claude -p` that never reached the API reports `is_error`, exits non-zero
    and leaves the working directory EMPTY. Persisting that would replace a real
    baseline with an empty one and record zeros as if they were token counts, so
    the harness stops instead: the operator gets the message the CLI returned
    (an expired OAuth session, typically), and `baseline/<ident>/` survives.
    """
    if not measured.get("claude_is_error") and measured.get("exit") == 0:
        return
    raise SystemExit(
        "claude run for %s produced no measurement (exit=%s): %s\n"
        "Nothing was written: baseline/%s is untouched. "
        "Fix the CLI (e.g. re-authenticate) and run again."
        % (ident, measured.get("exit"),
           measured.get("claude_error") or "no message in the payload", ident)
    )


# A throwaway prompt, used only to make the CLI state which model it runs. It
# is never written to a project.
PREFLIGHT_PROMPT = "Reply with exactly: ok"


def _read_json_string(text: str):
    """Parsed JSON, or `{}`: prose on stdout must not raise a traceback."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def _preflight_model(model: str) -> str:
    """Ask the CLI what `model` actually resolves to, or exit non-zero.

    The alias list belongs to the CLI and changes between versions — this build
    documents `fable`, `opus` and `sonnet`, and accepts full names like
    `claude-fable-5` — so a hardcoded list would rot within a release. The CLI
    is therefore asked once, on a throwaway prompt in a throwaway directory,
    and two things must hold before any baseline is started: the call must
    succeed, and the model the CLI reports must be the one requested. A model
    that does not exist, or one the CLI silently substitutes, stops the run
    here instead of after six promises and 30 minutes.
    """
    workdir = Path(tempfile.mkdtemp(prefix="claude_preflight_"))
    argv = [
        "claude", "-p", PREFLIGHT_PROMPT,
        "--permission-mode", "acceptEdits",
        "--output-format", "json",
        "--no-session-persistence",
        "--model", model,
    ]
    try:
        proc = subprocess.run(
            argv, cwd=str(workdir), capture_output=True, text=True,
            timeout=300, stdin=subprocess.DEVNULL, env=_clean_env(),
        )
    except subprocess.TimeoutExpired:
        raise SystemExit("preflight for --model %r timed out" % model)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    payload = _read_json_string(proc.stdout)
    if payload.get("is_error"):
        raise SystemExit(
            "refusing to run: --model %r failed the preflight: %s"
            % (model, payload.get("result") or proc.stderr.strip()[:200])
        )
    reported = _model_of(payload)
    if not reported or model not in reported:
        raise SystemExit(
            "refusing to run: --model %r resolved to %r, which is not the "
            "model that ran. A baseline filed under the wrong model name is "
            "worse than no baseline." % (model, reported)
        )
    return reported


def _refuse_wrong_model(ident: str, requested: str | None,
                        measured: dict) -> None:
    """Abort when a run's own payload names a model other than the requested one.

    The preflight covers the common case before any work is done; this covers
    the rest — a prompt that started on the right model and was moved by the
    CLI (an overload fallback, say), which would otherwise be filed silently
    under the requested label.
    """
    if not requested:
        return
    reported = measured.get("claude_model") or "?"
    if requested not in reported:
        raise SystemExit(
            "claude ran %r for %s while %r was requested; nothing was written"
            % (reported, ident, requested)
        )


def _profile(ident: str, model: str | None, destination_root: Path,
             reuse: bool = False) -> dict:
    workdir = WORK_ROOT / ident
    shutil.rmtree(workdir, ignore_errors=True)
    source = destination_root / ident

    record: dict = {
        "ident": ident,
        "required_entry": _required_entry(ident),
        "prompt_chars": _prompt_chars(ident),
    }
    if reuse:
        if not source.is_dir():
            raise SystemExit("nothing to reuse for %s at %s" % (ident, source))
        shutil.copytree(source, workdir)
        # A reuse run measures the GATES, not the generation: the timing AND
        # the token totals of the run that produced this output are recovered
        # from the sidecars it wrote, so the measurement survives a re-render
        # instead of being replaced by the word "reused".
        record.update(_load_run(destination_root, ident))
    else:
        workdir.mkdir(parents=True)
        measured, payload = _run_claude(ident, workdir, model)
        # Both checked BEFORE anything is written, so neither a failed run nor
        # a wrong-model run can cost the previous baseline its sources.
        _refuse_failed_run(ident, measured)
        _refuse_wrong_model(ident, model, measured)
        record.update(measured)
        _persist_run(destination_root, ident, record, payload)

    record["files"] = [
        p.relative_to(workdir).as_posix() for p in _python_files(workdir)
    ]
    # Measured BEFORE the shim is installed: the shim is harness scaffolding,
    # and counting it would credit Claude with source it never wrote.
    record["source_files"], record["source_chars"] = _source_chars(workdir)
    record["all_source_files"], record["all_source_chars"] = _source_chars_all(
        workdir)
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


def _cell(value) -> str:
    """A table cell for a possibly-unmeasured number.

    Floats are rounded because the CLI reports a cost sum with full float noise
    (`0.31652940000000007`), which is a measurement artifact, not precision.
    """
    if value is None:
        return "—"
    if isinstance(value, float):
        return "%.4f" % value
    return str(value)


def _usage_cell(rec: dict, key: str) -> str:
    return _cell((rec.get("claude_usage") or {}).get(key))


def _usage_sum(records: list[dict], key: str):
    """The column total, or None when any prompt in it was not measured.

    A total that silently omitted a prompt would be read as a sum over all six,
    so an incomplete column reports nothing instead of a smaller number.
    """
    if not records:
        return None
    total = 0
    for rec in records:
        value = (rec.get("claude_usage") or {}).get(key)
        if not isinstance(value, int):
            return None
        total += value
    return total


def _cost_sum(records: list[dict]):
    """Total measured cost, or None when any run did not report one."""
    if not records:
        return None
    total = 0.0
    for rec in records:
        value = rec["claude_cost_usd"]
        if not isinstance(value, (int, float)):
            return None
        total += value
    return round(total, 4)


def _failure_count(failures):
    """`None` = not applicable (entry file absent), else the number of failures."""
    if failures is None:
        return None
    return len(failures)


def _consumption_table(records: list[dict]) -> list[str]:
    """What the six runs consumed, in the units the payload actually provides.

    Chars and tokens are both printed because they are NOT the same claim:
    `source (chars)` is the deliverable, read back off disk — the one unit this
    harness and the generator's cost profile can both measure the same way —
    while the token columns are Claude's own accounting of its traffic, which
    the generator cannot fully reproduce (its streamed fills report no usage).
    """
    lines = [
        "## Consommation",
        "",
        "`prompt (chars)` : ce qui a été envoyé (fichier de prompt + consigne",
        "finale). `source (chars)` : le projet écrit, relu sur le disque après le",
        "run, **en ne comptant que les `.py`** — c'est l'unité du profil du",
        "générateur, donc la seule comparable ; le projet complet (README,",
        "`requirements.txt`) est donné dans le détail par prompt. Les colonnes",
        "`tokens` viennent de la comptabilité du CLI lui-même",
        "(`usage` du payload) : `entrée` EXCLUT le cache, et `cache lu` est le",
        "contexte relu à chaque tour — c'est là que passe le trafic d'une boucle",
        "d'agent, donc la colonne est conservée au lieu d'être fondue dans le",
        "total.",
        "",
        "| prompt | prompt (chars) | source (chars) | fichiers | tokens entrée"
        " | tokens sortie | cache lu | cache écrit | tokens total | coût (USD) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for rec in records:
        lines.append(
            "| `%s` | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                rec["ident"], _cell(rec["prompt_chars"]),
                _cell(rec["source_chars"]), _cell(rec["source_files"]),
                _usage_cell(rec, "input"), _usage_cell(rec, "output"),
                _usage_cell(rec, "cache_read"),
                _usage_cell(rec, "cache_creation"), _usage_cell(rec, "total"),
                _cell(rec["claude_cost_usd"]),
            )
        )
    lines.append(
        "| **total** | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
        % (
            _cell(sum(rec["prompt_chars"] for rec in records)),
            _cell(sum(rec["source_chars"] for rec in records)),
            _cell(sum(rec["source_files"] for rec in records)),
            _cell(_usage_sum(records, "input")),
            _cell(_usage_sum(records, "output")),
            _cell(_usage_sum(records, "cache_read")),
            _cell(_usage_sum(records, "cache_creation")),
            _cell(_usage_sum(records, "total")),
            _cell(_cost_sum(records)),
        )
    )
    lines.append("")
    return lines


def _summary_of(rec: dict) -> dict:
    """One record reduced to what a comparison document needs."""
    raw = rec["raw"] or {}
    return {
        "ident": rec["ident"],
        "model": rec["claude_model"],
        "elapsed_s": rec["elapsed_s"],
        "claude_duration_ms": rec.get("claude_duration_ms"),
        "claude_api_ms": rec.get("claude_api_ms"),
        "turns": rec["claude_turns"],
        "cost_usd": (
            round(rec["claude_cost_usd"], 6)
            if isinstance(rec["claude_cost_usd"], (int, float))
            else rec["claude_cost_usd"]
        ),
        "usage": rec.get("claude_usage"),
        "model_usage": rec.get("claude_model_usage") or {},
        "prompt_chars": rec["prompt_chars"],
        "source_files": rec["source_files"],
        "source_chars": rec["source_chars"],
        "all_source_files": rec["all_source_files"],
        "all_source_chars": rec["all_source_chars"],
        "python_files": len(rec["files"]),
        "stub_markers": len(rec["stub_markers"]),
        "compile_ok": not rec["compile"],
        "raw_functional": _failure_count(raw.get("functional")),
        "raw_conformity": _failure_count(raw.get("conformity")),
        "shim_functional": _failure_count(rec["shimmed"].get("functional")),
        "shim_conformity": _failure_count(rec["shimmed"].get("conformity")),
    }


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

    lines += _consumption_table(records)

    for rec in records:
        lines += [
            "## `%s`" % rec["ident"],
            "",
            "- durée murale : **%s s**" % rec["elapsed_s"],
            "- interne Claude : duration_ms=%s, tours=%s, coût=%s USD, modèle=%s"
            % (rec["claude_duration_ms"], rec["claude_turns"],
               _cell(rec["claude_cost_usd"]), rec["claude_model"]),
            "- exit=%s" % rec["exit"],
            "- consommation Claude : %s chars de prompt -> %s chars de source"
            " Python en %s fichiers (projet complet : %s fichiers, %s chars)"
            % (_cell(rec["prompt_chars"]), _cell(rec["source_chars"]),
               _cell(rec["source_files"]), _cell(rec["all_source_files"]),
               _cell(rec["all_source_chars"])),
            "- tokens Claude : entrée=%s, sortie=%s, cache lu=%s, cache écrit=%s,"
            " total=%s"
            % (_usage_cell(rec, "input"), _usage_cell(rec, "output"),
               _usage_cell(rec, "cache_read"), _usage_cell(rec, "cache_creation"),
               _usage_cell(rec, "total")),
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
        for model, entry in (rec.get("claude_model_usage") or {}).items():
            lines.append(
                "- tokens par modèle (`%s`) : entrée=%s, sortie=%s, cache lu=%s,"
                " cache écrit=%s, coût=%s USD"
                % (model, _cell(entry.get("input")), _cell(entry.get("output")),
                   _cell(entry.get("cache_read")),
                   _cell(entry.get("cache_creation")),
                   _cell(entry.get("cost_usd")))
            )
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
                        help="MODEL to run, and the sub-directory/report "
                             "suffix for it: the label IS the model selector")
    parser.add_argument("--reuse", action="store_true",
                        help="re-run the gates on the persisted output only")
    args = parser.parse_args(argv)

    from agentlib.bench.named_prompt_suite import NAMED_PROMPTS

    # `--label` SELECTS THE MODEL: `--label sonnet` must run Sonnet. An explicit
    # `--model` is allowed and must agree with it, because the label also names
    # the directory the output lands in — two different answers would file one
    # model's output under another model's name.
    if args.label:
        if args.model and args.model != args.label:
            raise SystemExit(
                "--label %r and --model %r disagree: the label selects the "
                "model AND names the output directory."
                % (args.label, args.model)
            )
        args.model = args.label
    if args.model and not args.reuse:
        # Hard failure BEFORE any run: a model that does not exist, or that the
        # CLI silently substitutes, stops here.
        print("model %r -> %s" % (args.model, _preflight_model(args.model)),
              flush=True)

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
    # The machine-readable twin, same convention as named_prompts_report: the
    # comparison document reads THIS instead of re-parsing the markdown, so a
    # number quoted there can always be traced back to the run that produced it.
    summary_path = ROOT / "analysis" / ("%s.json" % stem)
    summary_path.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": [_summary_of(rec) for rec in records],
        "totals": {
            "prompt_chars": sum(rec["prompt_chars"] for rec in records),
            "source_chars": sum(rec["source_chars"] for rec in records),
            "source_files": sum(rec["source_files"] for rec in records),
            "all_source_chars": sum(
                rec["all_source_chars"] for rec in records),
            "all_source_files": sum(
                rec["all_source_files"] for rec in records),
            "tokens_input": _usage_sum(records, "input"),
            "tokens_output": _usage_sum(records, "output"),
            "tokens_cache_read": _usage_sum(records, "cache_read"),
            "tokens_cache_creation": _usage_sum(records, "cache_creation"),
            "tokens_total": _usage_sum(records, "total"),
            "cost_usd": _cost_sum(records),
        },
    }, indent=2), encoding="utf-8")
    for rec in records:
        usage = rec.get("claude_usage") or {}
        print("  tokens=%s/%s (in/out) source=%s chars"
              % (usage.get("input", "?"), usage.get("output", "?"),
                 rec["source_chars"]))
    print("\nreport -> analysis/%s" % report_name)
    print("json   -> analysis/%s.json" % stem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
