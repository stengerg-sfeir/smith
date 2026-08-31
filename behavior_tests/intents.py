"""User-intent extraction for the facade (CLI/API) behavioural tester.

This is the FIRST stage of the new "facade" tester, built ALONGSIDE the
existing internal tester (``scenarios.py`` / ``runner.py``) rather than
replacing it.

A facade tester verifies that the app fulfils what a USER actually wants, at
the user-facing surface (the CLI today, an API later). So instead of auditing
internal entities/repos/services, it:

1. extracts USER INTENTIONS from the prompt (this module — ``extract_intentions``),
2. discovers the real FACADE (CLI surface) from the generated code
   (``facade_discovery.discover_facade``),
3. maps each intention to a concrete facade invocation + an observable
   assertion (later stage),
4. runs it in a subprocess and reports pass/fail (later stage).

``extract_intentions`` reads ONLY the prompt (never the code), so the intent
set is an independent, non-tautological oracle of what the user asked for.

The implementation now lives in ``agentlib.pipeline.intents`` (the generation
pipeline needs the same oracle as a deterministic CLI gate). This module
re-exports it so the facade tester keeps a stable import surface.
"""

from __future__ import annotations

from agentlib.pipeline.intents import (
    intent_schema,
    extract_intentions,
    compute_needs_cli,
    _INTENT_SYSTEM,
    _CLI_MARKERS,
    _prompt_specifies_cli,
)

__all__ = [
    "intent_schema",
    "extract_intentions",
    "compute_needs_cli",
    "_INTENT_SYSTEM",
    "_CLI_MARKERS",
    "_prompt_specifies_cli",
]
