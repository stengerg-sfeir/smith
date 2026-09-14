#!/usr/bin/env python3
"""Standalone semantic-oracle runner for the neurosymbolic bench.

Runs the EXECUTED semantic oracle (design-derived + spec-derived invariants,
see ``behavior_tests.semantic_oracle``) against a previously generated
project, then validates that the oracle is load-bearing by mutation
(``behavior_tests.mutate_semantic``). Independent of ``run_benchmark.py``.

Usage:
    python3 run_semantic_oracle.py
    python3 run_semantic_oracle.py --project expenses
    python3 run_semantic_oracle.py --no-mutate
"""

from __future__ import annotations

from behavior_tests.semantic_runner import main

if __name__ == "__main__":
    raise SystemExit(main())
