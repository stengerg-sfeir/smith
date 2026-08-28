#!/usr/bin/env python3
"""Standalone behavioral-test runner for the neurosymbolic bench.

This entry point is intentionally independent of ``run_benchmark.py``. It
generates behavior tests from the prompt SPEC (a separate LLM pass) and runs
them against a previously generated project, reporting per-test pass/fail and
a coverage matrix.

Usage:
    python3 run_behavior_tests.py --prompt 27
    python3 run_behavior_tests.py --start 21 --end 30
    python3 run_behavior_tests.py --all
    python3 run_behavior_tests.py --prompt 27 --use-cached-spec

The generated snapshot is frozen under ``behavior_runs/NNN/generated``, the
test spec under ``behavior_runs/NNN/test_spec.json`` and the deterministic
test file under ``behavior_runs/NNN/test_behavior.py``, so every run is
reproducible.
"""

from __future__ import annotations

from behavior_tests.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
