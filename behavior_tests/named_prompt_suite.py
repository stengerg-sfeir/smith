"""Per-prompt functional and conformance checks for the six NAMED prompts.

The two questions the brief asks about every named prompt are answered here,
deterministically and without an LLM:

* **functional** — the shipped project RUNS: every command the specification
  enumerates is invoked (required options only, then every option) in a
  scratch copy and must not dump a traceback; and the specification's own
  minimal workflow (add a row, list it) is executed end to end and must exit 0
  and surface what was just written.
* **conformant** — the shipped project says what the specification asked for:
  the command surface (``behavior_tests.conformity``), the repository surface
  (``behavior_tests.repo_conformity``), and — for the two script-like prompts
  — the properties the specification states in prose (a ``main()`` with type
  hints and the ``__main__`` guard; header-driven CSV keys, an optional output
  path, and no hard-coded column names).

Every check returns a list of human-readable FAILURES (``[]`` = pass), so the
driver can print a per-prompt verdict and write it to ``analysis/``.
"""

from __future__ import annotations

import ast
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from behavior_tests.conformity import (
    prompt_surface_paths,
    surface_conformity_violations,
)
from behavior_tests.repo_conformity import repository_conformity_violations
from agentlib.pipeline.cli_spec import extract_prompt_cli_commands, parse_prompt_command

NAMED_PROMPTS = (
    "cli_tool",
    "expenses",
    "hello_world",
    "inventory",
    "library_system",
    "multi_module",
)

# Prompts whose specification enumerates a click command line: the generic
# sweep and the CLI-conformity check apply to them.
_ENUMERATING = ("expenses", "inventory", "library_system")

# Prompts that are a single script rather than an entity-backed app.
_SCRIPTS = {
    "hello_world": "hello.py",
    "cli_tool": "csv_to_json.py",
}

_INT_PLACEHOLDER = "1"
_STR_PLACEHOLDER = "x"
_TIMEOUT = 90


def _run(project: Path, argv: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            [sys.executable] + argv,
            cwd=str(project), capture_output=True, text=True, timeout=_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", "TIMEOUT")


def _has_traceback(proc: subprocess.CompletedProcess) -> bool:
    return "Traceback (most recent call last)" in (proc.stderr or "")


# --- the generic sweep ------------------------------------------------------

def _all_args(options: list[str]) -> list[str]:
    """Every option given a placeholder value (value-less flags stay bare)."""
    out: list[str] = []
    for opt in options:
        if not opt.startswith("--") or "/" in opt or opt.startswith("--no-"):
            continue
        if opt.endswith(("-id", "-year", "-month")):
            out.extend([opt, _INT_PLACEHOLDER])
        elif opt in ("--recurring", "--available-only", "--active-only",
                     "--low-only"):
            out.append(opt)
        else:
            out.extend([opt, _STR_PLACEHOLDER])
    return out


def cli_sweep_failures(ident: str, source: Path) -> tuple[list[str], int]:
    """Invoke every enumerated command; a traceback is a failure."""
    scratch = Path(tempfile.mkdtemp(prefix="named_sweep_"))
    failures: list[str] = []
    n_runs = 0
    try:
        project = scratch / ident
        shutil.copytree(source, project)
        for db in project.glob("*.db"):
            db.unlink()
        prompt_text = (Path("prompts") / ("prompt_%s.txt" % ident)).read_text(
            encoding="utf-8")
        for command in prompt_surface_paths(prompt_text):
            path_args = command["path"].split()
            for extra in ([], ["--help"], _all_args(command.get("options") or [])):
                n_runs += 1
                proc = _run(project, ["cli.py"] + path_args + extra)
                if _has_traceback(proc):
                    tail = (proc.stderr or "").strip().splitlines()[-1:]
                    failures.append(
                        "%s %s -> traceback: %s"
                        % (command["path"], " ".join(extra) or "<no option>",
                           tail[0] if tail else "")
                    )
                elif proc.returncode not in (0, 1, 2):
                    failures.append(
                        "%s %s -> exit=%d (no traceback, but not 0/1/2)"
                        % (command["path"], " ".join(extra) or "<no option>",
                           proc.returncode)
                    )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return failures, n_runs


def _cli(project: Path, args: list[str]) -> subprocess.CompletedProcess:
    return _run(project, ["cli.py"] + args)


def _cli_db_path(project: Path) -> Path | None:
    """The database file the shipped CLI itself opens (``DB_PATH`` in cli.py).

    Never guessed: ``library_system`` ships an EMPTY ``app.db`` beside the real
    ``library.db``, so seeding "the first *.db" writes to a database no command
    reads.
    """
    cli = project / "cli.py"
    if not cli.is_file():
        return None
    match = re.search(
        r"(?m)^DB_PATH\s*=\s*['\"]([^'\"]+)['\"]",
        cli.read_text(encoding="utf-8"),
    )
    if match:
        return project / match.group(1)
    dbs = sorted(project.glob("*.db"))
    return dbs[0] if dbs else None


def _seed_parent(project: Path, sql: str) -> None:
    """Seed a parent row directly (a workflow's prerequisite the spec's own
    command list may not expose — library_system has no ``author add``)."""
    db = _cli_db_path(project)
    if db is None:
        return
    conn = sqlite3.connect(str(db))
    try:
        conn.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _id_option(project: Path, command: list[str]) -> str:
    """The id option the shipped CLI declares for ``command``.

    For a specification that ENUMERATES its options the prompt's own spelling
    is the contract (and the conformity gate proves the CLI matches it); for a
    specification that only names its COMMANDS (``multi_module``) the option
    name is a design decision, so it is read from the CLI's own help text
    instead of guessed.
    """
    proc = _run(project, ["cli.py"] + command + ["--help"])
    match = re.search(r"(--[a-z0-9_-]*id)\b", proc.stdout or "")
    return match.group(1) if match else "--id"


def _workflow_failures(ident: str, source: Path) -> list[str]:
    """The specification's own minimal workflow, executed for real."""
    scratch = Path(tempfile.mkdtemp(prefix="named_flow_"))
    failures: list[str] = []
    try:
        project = scratch / ident
        shutil.copytree(source, project)
        for db in project.glob("*.db"):
            db.unlink()
        steps: list[tuple[list[str], int, str | None]] = []
        if ident == "expenses":
            steps = [
                (["expense", "category", "add", "--name", "food",
                  "--description", "meals"], 0, None),
                (["expense", "add", "--amount", "12.34", "--description",
                  "lunch", "--category", "1"], 0, None),
                (["expense", "list"], 0, "lunch"),
            ]
        elif ident == "inventory":
            # Option names are the PROMPT's own: `product add --sku --name
            # --category --price --stock`. The money value is a COUNT OF CENTS:
            # this specification declares only the STORAGE half of the cents
            # convention ("stored as integers (cents)"), never the decimal
            # display/input half, so the option is an int and `999` is the
            # correct input (`money_display_enabled` requires both halves).
            steps = [
                (["category", "add", "--name", "tools"], 0, None),
                (["product", "add", "--sku", "S1", "--name", "hammer",
                  "--category", "1", "--price", "999", "--stock", "5"],
                 0, None),
                (["product", "list"], 0, "hammer"),
            ]
        elif ident == "library_system":
            # The schema is created by a real command (Database._init_tables),
            # and ONLY then can a parent row the command surface cannot create
            # be seeded — this specification has no `author add`.
            _cli(project, ["library", "member", "list"])
            _seed_parent(
                project,
                "INSERT INTO authors (name, birth_year, biography) "
                "VALUES ('Frank Herbert', 1920, 'dune')",
            )
            steps = [
                (["library", "book", "add", "--title", "Dune", "--isbn",
                  "9780441013593", "--author-id", "1", "--published-year",
                  "1965", "--copies", "2"], 0, None),
                (["library", "book", "list"], 0, "Dune"),
                (["library", "book", "search", "--query", "Dune"], 0, "Dune"),
            ]
        if not steps:
            return []
        for args, want_exit, want_text in steps:
            proc = _cli(project, args)
            label = " ".join(args)
            if proc.returncode != want_exit:
                failures.append(
                    "%s -> exit=%d (want %d) %s"
                    % (label, proc.returncode, want_exit,
                       (proc.stderr or "").strip().splitlines()[-1:] or "")
                )
                continue
            if want_text and want_text not in (proc.stdout or ""):
                failures.append(
                    "%s -> output does not contain %r" % (label, want_text)
                )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return failures


# --- the two script-like specifications -------------------------------------

def _hello_world(project: Path) -> tuple[list[str], list[str]]:
    functional: list[str] = []
    conformant: list[str] = []
    script = project / _SCRIPTS["hello_world"]
    if not script.is_file():
        return ["hello_world: no %s" % script.name], ["hello_world: no script"]
    proc = _run(project, [script.name])
    if proc.returncode != 0:
        functional.append(
            "running %s -> exit=%d %s"
            % (script.name, proc.returncode, (proc.stderr or "").strip()[-200:])
        )
    if "Hello, World!" not in (proc.stdout or ""):
        functional.append(
            "running %s did not print 'Hello, World!' (got %r)"
            % (script.name, (proc.stdout or "").strip()[:80])
        )
    text = script.read_text(encoding="utf-8")
    if not re.search(r"(?m)^if __name__ == ['\"]__main__['\"]:", text):
        conformant.append("hello_world: the __main__ guard is absent")
    tree = ast.parse(text)
    mains = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "main"
    ]
    if not mains:
        conformant.append("hello_world: no main() function")
    else:
        fn = mains[0]
        if fn.returns is None and not any(
            a.annotation is not None for a in fn.args.args
        ):
            conformant.append(
                "hello_world: main() carries NO type hint, and the "
                "specification asks for type hints throughout"
            )
    return functional, conformant


def _cli_tool(project: Path) -> tuple[list[str], list[str]]:
    functional: list[str] = []
    conformant: list[str] = []
    script = project / _SCRIPTS["cli_tool"]
    if not script.is_file():
        return ["cli_tool: no %s" % script.name], ["cli_tool: no script"]
    text = script.read_text(encoding="utf-8")

    scratch = Path(tempfile.mkdtemp(prefix="named_csv_"))
    try:
        csv_path = Path(scratch) / "data.csv"
        csv_path.write_text("alpha,beta\ngamma,delta\n", encoding="utf-8")
        # Header-driven keys, printed to stdout when no --output is given.
        proc = _run(project, [script.name, str(csv_path)])
        if proc.returncode != 0:
            functional.append(
                "cli_tool: run -> exit=%d %s"
                % (proc.returncode, (proc.stderr or "").strip()[-200:])
            )
        else:
            for key in ("alpha", "beta"):
                if key not in (proc.stdout or ""):
                    functional.append(
                        "cli_tool: stdout lacks the header key %r (the header "
                        "row must drive the keys)" % key
                    )
        # An optional output path writes the file.
        out_path = Path(scratch) / "out.json"
        proc2 = _run(project, [script.name, str(csv_path), "--output", str(out_path)])
        if proc2.returncode == 0 and out_path.is_file():
            if "alpha" not in out_path.read_text(encoding="utf-8"):
                functional.append("cli_tool: --output file lacks the header keys")
        elif proc2.returncode == 0:
            functional.append("cli_tool: --output did not write a file")
        # A missing input must be a clean error, never a traceback.
        missing = _run(project, [script.name, str(Path(scratch) / "absent.csv")])
        if _has_traceback(missing):
            functional.append("cli_tool: a missing input file dumps a traceback")
        if missing.returncode == 0:
            functional.append("cli_tool: a missing input file exits 0")
        # A malformed CSV must be a clean error too.
        bad = Path(scratch) / "bad.csv"
        bad.write_text('a,b\n"unterminated,2\n', encoding="utf-8")
        malformed = _run(project, [script.name, str(bad)])
        if _has_traceback(malformed):
            functional.append("cli_tool: a malformed CSV dumps a traceback")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    if not re.search(r"DictReader|fieldnames|next\(\s*reader", text):
        conformant.append(
            "cli_tool: the header row is not read (no DictReader/fieldnames)"
        )
    for literal in ('"title"', "'title'", '"name"', "'name'"):
        if literal in text:
            conformant.append(
                "cli_tool: hard-codes the column name %s, which the "
                "specification forbids" % literal
            )
    if "--output" not in text:
        conformant.append("cli_tool: no optional output path option")
    if "import sqlite3" in text:
        conformant.append(
            "cli_tool: imports sqlite3, which this specification never asks for"
        )
    return functional, conformant


# --- the public entry points -------------------------------------------------

def functional_failures(ident: str, project: Path) -> tuple[list[str], dict]:
    """Everything about ``the code works``. Returns (failures, metrics)."""
    metrics: dict = {}
    if ident in _SCRIPTS:
        failures, _ = (
            _hello_world(project) if ident == "hello_world" else _cli_tool(project)
        )
        return failures, metrics
    if ident in _ENUMERATING:
        sweep, n_runs = cli_sweep_failures(ident, project)
        metrics["sweep_runs"] = n_runs
        return sweep + _workflow_failures(ident, project), metrics
    # multi_module: a CLI surface the prompt describes in prose, not as a list.
    return _multi_module_functional(project), metrics


def _multi_module_functional(project: Path) -> list[str]:
    scratch = Path(tempfile.mkdtemp(prefix="named_mm_"))
    failures: list[str] = []
    try:
        work = scratch / "multi_module"
        shutil.copytree(project, work)
        for db in work.glob("*.db"):
            db.unlink()
        # This specification names its COMMANDS, not their options: the id
        # option's spelling is a design decision, so it is read from the CLI.
        id_opt = _id_option(work, ["show"])
        steps: list[tuple[list[str], int, str | None]] = [
            (["add", "--title", "write tests", "--description", "d"], 0, None),
            (["list"], 0, "write tests"),
            (["show", id_opt, "1"], 0, None),
            (["update", id_opt, "1", "--status", "done"], 0, None),
            (["list", "--status", "done"], 0, None),
            (["delete", id_opt, "1"], 0, None),
        ]
        for args, want_exit, want_text in steps:
            proc = _cli(work, args)
            label = " ".join(args)
            if proc.returncode != want_exit:
                failures.append(
                    "%s -> exit=%d (want %d) %s"
                    % (label, proc.returncode, want_exit,
                       (proc.stderr or "").strip().splitlines()[-1:] or "")
                )
            elif want_text and want_text not in (proc.stdout or ""):
                failures.append("%s -> output lacks %r" % (label, want_text))
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return failures


def conformity_failures(ident: str, project: Path) -> list[str]:
    """Everything about ``it respects the prompt``."""
    prompt_text = (Path("prompts") / ("prompt_%s.txt" % ident)).read_text(
        encoding="utf-8")
    failures: list[str] = []
    if ident in _SCRIPTS:
        _, conf = (
            _hello_world(project) if ident == "hello_world" else _cli_tool(project)
        )
        return conf
    if prompt_surface_paths(prompt_text):
        failures += surface_conformity_violations(prompt_text, project)
    failures += repository_conformity_violations(prompt_text, project)
    if ident == "multi_module":
        failures += _multi_module_conformity(project, prompt_text)
    return failures


_MULTI_MODULE_COMMANDS = ("add", "list", "update", "delete", "show")
_STATUS_VOCABULARY = ("todo", "in_progress", "done")
_TASK_FIELDS = ("title", "description", "status", "created_at")


def _multi_module_conformity(project: Path, prompt_text: str) -> list[str]:
    failures: list[str] = []
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(project.glob("*.py"))
    )
    for name in _MULTI_MODULE_COMMANDS:
        if not re.search(r"(?m)^\s*def\s+%s\s*\(" % name, blob):
            failures.append("multi_module: the CLI command %r is absent" % name)
    for value in _STATUS_VOCABULARY:
        if value not in blob:
            failures.append(
                "multi_module: the status vocabulary value %r is absent" % value
            )
    model = project / "models.py"
    if model.is_file():
        text = model.read_text(encoding="utf-8")
        for field in _TASK_FIELDS:
            if field not in text:
                failures.append(
                    "multi_module: the Task model lacks the field %r" % field
                )
    else:
        failures.append("multi_module: no models.py")
    service = sorted(project.glob("*_service.py"))
    if not service:
        failures.append("multi_module: no service module")
    else:
        svc = service[0].read_text(encoding="utf-8")
        for verb in ("add", "update", "list"):
            if not re.search(r"def\s+\w*%s\w*\s*\(" % verb, svc):
                failures.append(
                    "multi_module: the service has no %r operation" % verb
                )
    return failures


def enumerated_command_names(prompt_text: str) -> list[str]:
    """The command paths the specification itself lists (for the report)."""
    out: list[str] = []
    for text in extract_prompt_cli_commands(prompt_text):
        command = parse_prompt_command(text)
        if command is not None:
            out.append(" ".join(list(command["group"]) + [command["name"]]))
    return out
