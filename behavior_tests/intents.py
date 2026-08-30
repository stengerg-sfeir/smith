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
"""

from __future__ import annotations

import re

from agentlib.config import LLM_MAX_TOKENS_LONG
from agentlib.llm.client import _json_complete


def intent_schema():
    """Schema for the user-intent extraction pass."""
    return {
        "type": "object",
        "properties": {
            "intentions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "intent_id": {"type": "string"},
                        "text": {"type": "string"},
                        "cli_command": {"type": "string"},
                        "requires": {"type": "string"},
                        "observable": {"type": "string"},
                        "spec_level": {
                            "type": "string",
                            "enum": ["explicit", "partial", "vague"],
                        },
                    },
                    "required": ["intent_id", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["intentions"],
        "additionalProperties": False,
    }


_INTENT_SYSTEM = (
    "You are an expert requirement analyst. Given a software specification, "
    "extract the USER-FACING INTENTIONS it implies.\n\n"
    "An INTENTION is one capability a real user wants from the product, "
    "expressed as a goal and observable at the user-facing surface (the CLI / "
    "API). Emit one intention per distinct user capability.\n\n"
    "- intent_id: a short id, e.g. I1, I2, ...\n"
    "- text: the user goal in natural language, e.g. \"I can add a product to "
    "the inventory\".\n"
    "- cli_command: the command(s) the SPEC explicitly gives for this "
    "capability, VERBATIM as written in the spec. If the spec does NOT "
    "explicitly name a command/interface, leave this empty.\n"
    "- requires: what inputs/data the capability needs to be exercised (e.g. "
    "\"a product with sku, name, category, price, stock\"), or empty.\n"
    "- observable: what the user observes on success (stdout, exit, a file, "
    "an updated list...).\n"
    "- spec_level: how directly testable this is from the spec alone:\n"
    "    explicit  = the spec names the command and its inputs;\n"
    "    partial   = the spec names the command but not its exact args, or "
    "describes behaviour functionally;\n"
    "    vague     = the spec gives no command/interface or leaves the "
    "behaviour almost entirely unspecified.\n\n"
    "Do NOT emit separate intentions for trivially-related aspects of one "
    "capability unless they are genuinely distinct user goals. Do NOT invent "
    "commands the spec does not mention. Read ONLY the spec — never the code."
)


_CLI_MARKERS = re.compile(
    r"\b(click|argparse|command|cli)\b|--[A-Za-z_]",
    re.IGNORECASE,
)


def _prompt_specifies_cli(prompt_text: str) -> bool:
    """Heuristic: does the spec actually name a command-line interface?

    The intent extractor must not claim a ``cli_command`` for a prompt that
    never mentions one (e.g. prompt_20 describes capabilities but no CLI). A
    missing marker means any ``cli_command`` the LLM filled in is an
    hallucinated method name, not a real user-facing command.
    """
    return bool(_CLI_MARKERS.search(prompt_text or ""))


def extract_intentions(prompt_text: str, verbose: bool = False) -> list[dict]:
    """Return a list of ``{intent_id, text, cli_command, requires,
    observable, spec_level}`` user intentions.

    Reads ONLY the prompt (never the design/code), so the intent set is an
    independent oracle of what the user asked for at the facade level.

    Post-processing: if the spec never names a command-line interface, any
    ``cli_command`` the LLM invented is stripped and ``spec_level`` is
    downgraded from ``explicit`` to ``partial`` (the capability is stated but
    the facade is not) — the prompt is NOT explicitly testable at the CLI.
    """
    user = "SPECIFICATION:\n%s\n\nExtract the user intentions now." % prompt_text
    messages = [
        {"role": "system", "content": _INTENT_SYSTEM},
        {"role": "user", "content": user},
    ]
    for _ in range(2):
        data = _json_complete(
            messages, schema=intent_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG,
        )
        if isinstance(data, dict) and isinstance(data.get("intentions"), list):
            specifies_cli = _prompt_specifies_cli(prompt_text)
            out = []
            for i, it in enumerate(data["intentions"]):
                if not isinstance(it, dict):
                    continue
                text = it.get("text")
                if not isinstance(text, str) or not text.strip():
                    continue
                intent_id = it.get("intent_id")
                if not isinstance(intent_id, str) or not intent_id:
                    intent_id = "I%d" % (i + 1)
                lvl = it.get("spec_level")
                if lvl not in ("explicit", "partial", "vague"):
                    lvl = "vague"
                cli = (it.get("cli_command") or "").strip()
                if not specifies_cli:
                    # The prompt never names a CLI -> not explicitly testable.
                    cli = ""
                    if lvl == "explicit":
                        lvl = "partial"
                out.append({
                    "intent_id": intent_id,
                    "text": text.strip(),
                    "cli_command": cli,
                    "requires": (it.get("requires") or "").strip(),
                    "observable": (it.get("observable") or "").strip(),
                    "spec_level": lvl,
                })
            return out
        if verbose:
            print("    [intent-oracle] retrying…")
    return []
