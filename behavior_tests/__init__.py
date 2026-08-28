"""Independent behavioral test generation for the neurosymbolic bench.

This package is deliberately decoupled from ``run_benchmark.py`` and
``checks/generic_checks.py``. It generates *behavioral* assertions from the
prompt specification independently of the code generator, so the resulting
tests are a non-tautological oracle for the generated application.

The test pipeline is:

    prompt_N.txt --> (schema-constrained LLM pass) --> test_spec.json
    test_spec.json --> (deterministic renderer) --> test_behavior.py
    test_behavior.py --> (subprocess against generated/NN) --> JSON result

and the whole thing can be run independently via
``python3 run_behavior_tests.py --prompt NN`` (or ``--all`` / ``--start`` /
``--end``). It does not depend on ``run_benchmark.py``.
"""

from __future__ import annotations

__all__ = [
    "spec_schema",
    "oracle",
    "renderer",
    "runner",
]
