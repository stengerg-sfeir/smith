#!/usr/bin/env python3
"""Single entry point for the bench — every tester in ``agentlib/bench``.

``agent.py`` is the generator; this is the tester. Run any suite with:

    python3 bench.py <command> [suite options]

The arguments after the command are forwarded verbatim to the suite's own
parser, so every suite keeps its options (``--prompt``, ``--only``, ``--out``,
...). Run ``python3 bench.py --help`` for the command list.

The suites resolve ``prompts/``, ``generated/``, ``analysis/`` and
``behavior_runs/`` against the CURRENT DIRECTORY, so run this from the
repository root (exactly as the old ``run_*.py`` scripts required).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# The repository root, resolved from THIS file: put on sys.path so the suites
# import their own package (agentlib.*) whatever the cwd.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# command -> (module, one-line description)
COMMANDS: dict[str, tuple[str, str]] = {
    "named": (
        "agentlib.bench.cmd_named_prompts",
        "the six named prompts: generate, verify (functional + conformity + facade)",
    ),
    "surface": (
        "agentlib.bench.cmd_surface_smoke",
        "CLI surface smoke gate: no authorized command may dump a traceback (no LLM)",
    ),
    "cli-conformity": (
        "agentlib.bench.cmd_cli_conformity",
        "prompt -> CLI surface name conformity (deterministic)",
    ),
    "repo-conformity": (
        "agentlib.bench.cmd_repo_conformity",
        "prompt -> repository surface conformity (deterministic)",
    ),
    "semantic": (
        "agentlib.bench.cmd_semantic_oracle",
        "executed semantic oracle, validated by mutation",
    ),
    "behavior": (
        "agentlib.bench.cmd_behavior",
        "behavioral tests generated from the prompt spec (LLM)",
    ),
    "cli-behavior": (
        "agentlib.bench.cmd_cli_behavior",
        "CLI reachability and behaviour suite",
    ),
    "facade-intents": (
        "agentlib.bench.cmd_facade_intents",
        "extract user intentions + discover the CLI facade per prompt (LLM)",
    ),
    "facade-exec": (
        "agentlib.bench.cmd_facade_execution",
        "map the stored intentions to CLI invocations and execute them",
    ),
    "facade-all": (
        "agentlib.bench.cmd_facade_all",
        "facade intents then execution, in batches",
    ),
    "cost": (
        "agentlib.bench.cmd_cost_profile",
        "per-phase generation cost profile (wall time attribution)",
    ),
    "claude": (
        "agentlib.bench.cmd_claude_baseline",
        "Claude baseline runner (external model, for comparison)",
    ),
    "floors": (
        "agentlib.bench.cmd_generation_floors_unit",
        "generation floors unit tests (annotations, entry point)",
    ),
    "pruners": (
        "agentlib.bench.cmd_repo_pruner_unit",
        "repository-pruner unit tests",
    ),
}


def _usage(stream) -> None:
    print((__doc__ or "Single entry point for the bench.").strip(), file=stream)
    print("\ncommands:", file=stream)
    width = max(len(name) for name in COMMANDS)
    for name, (_, desc) in COMMANDS.items():
        print("  %-*s  %s" % (width, name, desc), file=stream)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        _usage(sys.stdout)
        return 0
    name, rest = args[0], args[1:]
    entry = COMMANDS.get(name)
    if entry is None:
        print("bench: unknown command %r" % name, file=sys.stderr)
        _usage(sys.stderr)
        return 2
    module = importlib.import_module(entry[0])
    return int(module.main(rest) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
