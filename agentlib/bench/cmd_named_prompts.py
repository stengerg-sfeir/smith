#!/usr/bin/env python3
"""Regenerate every NAMED prompt, verify it, and report to ``analysis/``.

For each named prompt this runner answers the two questions of the brief and
records the third piece of data asked for — the generation time:

1. **does the generated code work** (``agentlib.bench.named_prompt_suite``:
   the prompt's own commands swept for crashes, plus the prompt's minimal
   workflow executed for real; the LLM-driven facade is run as an independent
   second opinion);
2. **does it respect the prompt** (the command surface, the repository surface,
   and the properties each specification states in prose);
3. **how long the generation took** (wall clock around ``agent.py``).

The report is written to ``analysis/named_prompts_report.md`` (readable) and
``analysis/named_prompts_report.json`` (machine-readable).

Usage:
    python3 run_named_prompts.py                       # all six, regenerate
    python3 run_named_prompts.py --only expenses        # one prompt
    python3 run_named_prompts.py --skip-generate        # verify what is there
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agentlib.bench.named_prompt_suite import (
    NAMED_PROMPTS,
    conformity_failures,
    enumerated_command_names,
    functional_failures,
)

GENERATED_ROOT = Path("generated")
PROMPTS_DIR = Path("prompts")
ANALYSIS_DIR = Path("analysis")
LOG_DIR = Path("/tmp/named_prompt_logs")

# The official marker set: any hit means the generator silently degraded a
# method instead of rendering (or filling) it.
_FORBIDDEN = re.compile(
    r"reject|dropped \(unknown target\)|dropped \(no designed service method\)"
    r"|still stubbed|reverted|sanitized|dropped infeasible"
)


def generate(ident: str) -> dict:
    """Run the generator for one prompt, timing it."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / ("%s.log" % ident)
    started = time.monotonic()
    proc = subprocess.run(
        [sys.executable, "agent.py", "--prompt", ident],
        capture_output=True, text=True,
    )
    elapsed = time.monotonic() - started
    log.write_text((proc.stdout or "") + (proc.stderr or ""), encoding="utf-8")
    return {
        "elapsed_s": round(elapsed, 1),
        "exit": proc.returncode,
        "log": str(log),
    }


def marker_hits(log_path: str) -> list[str]:
    try:
        text = Path(log_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ["log unreadable"]
    return [ln.strip() for ln in text.splitlines() if _FORBIDDEN.search(ln)]


def compile_failures(project: Path) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(project)],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return []
    return ["compileall -> exit=%d %s"
            % (proc.returncode, (proc.stderr or "").strip()[-300:])]


def facade_status(ident: str) -> dict:
    """The LLM-driven facade, as an independent execution check."""
    proc = subprocess.run(
        [sys.executable, "bench.py", "facade-exec", "--prompt", ident],
        capture_output=True, text=True,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    line = next(
        (ln for ln in text.splitlines() if ln.startswith("[%s] status=" % ident)),
        "",
    )
    if not line:
        return {"status": "no_result", "detail": text.strip()[-200:]}
    fields = dict(re.findall(r"(\w+)=(\S+)", line))
    return {
        "status": fields.get("status", "?"),
        "mapped": fields.get("mapped", "?"),
        "pass": fields.get("pass", "?"),
        "fail": fields.get("fail", "?"),
    }


def verify(ident: str, project: Path) -> dict:
    func_failures, metrics = functional_failures(ident, project)
    conf_failures = conformity_failures(ident, project)
    prompt_text = (PROMPTS_DIR / ("prompt_%s.txt" % ident)).read_text(
        encoding="utf-8")
    return {
        "functional_failures": func_failures,
        "conformity_failures": conf_failures,
        "metrics": metrics,
        "enumerated_commands": enumerated_command_names(prompt_text),
    }


def _verdict(failures: list[str]) -> str:
    return "**PASS**" if not failures else "**FAIL (%d)**" % len(failures)


def render_report(records: list[dict]) -> str:
    lines = [
        "# Prompts nommés — génération, fonctionnel, conformité",
        "",
        "Chaque prompt nommé a été **régénéré** avec le générateur courant, puis",
        "vérifié sur les deux axes demandés. La colonne *Génération* est le temps",
        "mur de `agent.py --prompt <nom>`.",
        "",
        "| prompt | génération (s) | marqueurs | compile | **fonctionnel** | **conforme** | façade |",
        "|---|---|---|---|---|---|---|",
    ]
    for rec in records:
        fac = rec["facade"]
        lines.append(
            "| `%s` | %s | %s | %s | %s | %s | %s %s/%s |"
            % (
                rec["ident"],
                rec["elapsed_s"],
                "propre" if not rec["markers"] else "**%d**" % len(rec["markers"]),
                "OK" if not rec["compile_failures"]
                else "**%d**" % len(rec["compile_failures"]),
                _verdict(rec["functional_failures"]),
                _verdict(rec["conformity_failures"]),
                fac.get("status", "?"), fac.get("pass", "?"), fac.get("mapped", "?"),
            )
        )
    for rec in records:
        lines += ["", "## `%s`" % rec["ident"], ""]
        lines.append("- génération : **%s s** (exit %s)"
                     % (rec["elapsed_s"], rec["exit"]))
        cmds = rec["enumerated_commands"]
        if cmds:
            lines.append("- commandes énumérées par le prompt : %d — %s"
                         % (len(cmds), ", ".join("`%s`" % c for c in cmds)))
        else:
            lines.append("- le prompt n'énumère pas de ligne de commande")
        if rec["metrics"].get("sweep_runs"):
            lines.append("- balayage de surface : %d invocations"
                         % rec["metrics"]["sweep_runs"])
        lines.append("- marqueurs interdits : %s"
                     % ("aucun" if not rec["markers"] else "; ".join(rec["markers"])))
        lines.append("- compile : %s"
                     % ("OK" if not rec["compile_failures"]
                        else "; ".join(rec["compile_failures"])))
        lines.append("- **fonctionnel** : %s"
                     % ("PASS" if not rec["functional_failures"]
                        else "FAIL\n" + "\n".join(
                            "  - " + f for f in rec["functional_failures"])))
        lines.append("- **conforme** : %s"
                     % ("PASS" if not rec["conformity_failures"]
                        else "FAIL\n" + "\n".join(
                            "  - " + f for f in rec["conformity_failures"])))
        fac = rec["facade"]
        lines.append("- façade (contrôle indépendant, piloté par LLM) : status=%s "
                     "pass=%s/%s" % (fac.get("status"), fac.get("pass"),
                                     fac.get("mapped")))
    lines += ["", "_Généré le %s._" % datetime.now(timezone.utc).isoformat(), ""]
    return "\n".join(lines)


def _empty_record(ident: str, gen: dict, why: str) -> dict:
    return {
        "ident": ident, "elapsed_s": gen["elapsed_s"], "exit": gen["exit"],
        "markers": [why], "compile_failures": [why],
        "functional_failures": [why], "conformity_failures": [why],
        "metrics": {}, "enumerated_commands": [], "facade": {},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append",
                        help="Only these prompts (repeatable)")
    parser.add_argument("--skip-generate", action="store_true",
                        help="Verify the current trees without regenerating")
    args = parser.parse_args(argv)

    idents = list(NAMED_PROMPTS)
    if args.only:
        wanted = set(args.only)
        idents = [i for i in idents if i in wanted]

    # A `--only` run verifies a SUBSET; the records of the prompts it does not
    # touch are carried over, so a single re-run never discards the measured
    # generation time of the others.
    previous: dict[str, dict] = {}
    report_json = ANALYSIS_DIR / "named_prompts_report.json"
    if report_json.is_file():
        try:
            data = json.loads(report_json.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        previous = {
            r["ident"]: r for r in data.get("records", [])
            if isinstance(r, dict) and r.get("ident")
        }

    fresh: dict[str, dict] = {}
    for ident in idents:
        print("\n=== %s ===" % ident, flush=True)
        if args.skip_generate:
            # Re-verify WITHOUT regenerating, keeping the generation time of
            # the run that produced the tree being verified.
            prev = previous.get(ident) or {}
            gen = {"elapsed_s": prev.get("elapsed_s"),
                   "exit": prev.get("exit"), "log": ""}
        else:
            gen = generate(ident)
        project = GENERATED_ROOT / ident
        if not project.is_dir():
            print("  no generated project %s" % project, flush=True)
            fresh[ident] = _empty_record(ident, gen, "no generated project")
            continue
        markers = marker_hits(gen["log"]) if gen["log"] else []
        comp = compile_failures(project)
        ver = verify(ident, project)
        fac = facade_status(ident)
        fresh[ident] = {
            "ident": ident, "elapsed_s": gen["elapsed_s"], "exit": gen["exit"],
            "markers": markers, "compile_failures": comp, "facade": fac, **ver,
        }
        print("  gen=%ss markers=%d compile=%d functional=%d conforme=%d facade=%s"
              % (gen["elapsed_s"], len(markers), len(comp),
                 len(ver["functional_failures"]), len(ver["conformity_failures"]),
                 fac.get("status")), flush=True)

    # One record per named prompt, in the canonical order: the ones just
    # measured, then the ones carried over from an earlier run.
    records: list[dict] = [
        fresh[i] if i in fresh else previous[i]
        for i in NAMED_PROMPTS
        if i in fresh or i in previous
    ]

    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    (ANALYSIS_DIR / "named_prompts_report.json").write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                    "records": records}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report = ANALYSIS_DIR / "named_prompts_report.md"
    report.write_text(render_report(records), encoding="utf-8")
    print("\nreport -> %s" % report, flush=True)

    n_bad = sum(
        1 for r in records
        if r["markers"] or r["compile_failures"]
        or r["functional_failures"] or r["conformity_failures"]
    )
    print("[named-prompts] %d/%d prompt(s) clean"
          % (len(records) - n_bad, len(records)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
