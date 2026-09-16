#!/usr/bin/env python3
"""Standalone behavioral-test runner for the neurosymbolic bench.

This entry point generates behavior tests from the prompt SPEC (a separate
LLM pass) and runs them against a previously generated project, reporting
per-test pass/fail and a coverage matrix.

Usage:
    python3 bench.py behavior --prompt 27
    python3 bench.py behavior --start 21 --end 30
    python3 bench.py behavior --all
    python3 bench.py behavior --prompt 27 --use-cached-spec

The generated snapshot is frozen under ``behavior_runs/NNN/generated``, the
test spec under ``behavior_runs/NNN/test_spec.json`` and the deterministic
test file under ``behavior_runs/NNN/test_behavior.py``, so every run is
reproducible.
"""

from __future__ import annotations

from agentlib.bench.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
