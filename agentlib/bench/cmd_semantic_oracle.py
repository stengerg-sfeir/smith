#!/usr/bin/env python3
"""Standalone semantic-oracle runner for the neurosymbolic bench.

Runs the EXECUTED semantic oracle (design-derived + spec-derived invariants,
see ``agentlib.bench.semantic_oracle``) against a previously generated
project, then validates that the oracle is load-bearing by mutation
(``agentlib.bench.mutate_semantic``).

Usage:
    python3 run_semantic_oracle.py
    python3 run_semantic_oracle.py --project expenses
    python3 run_semantic_oracle.py --no-mutate
"""

from __future__ import annotations

from agentlib.bench.semantic_runner import main

if __name__ == "__main__":
    raise SystemExit(main())
