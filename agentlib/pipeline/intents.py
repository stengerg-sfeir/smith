"""User-intent extraction + deterministic CLI gate (generation-side).

This module is the AGENTLIB home of the intention oracle. It is used in two
places:

1. The facade tester (``behavior_tests``) extracts USER INTENTIONS from a
   prompt to verify the generated app fulfils what a user actually wants at
   the user-facing surface (``extract_intentions``).
2. The generation pipeline (``agentlib.pipeline.manifest``) now uses the SAME
   intention oracle as a DETERMINISTIC gate (``compute_needs_cli``) to decide
   whether a command-line surface must be synthesized: if the extracted user
   intentions describe data-management capabilities (CRUD, reports, exports),
   the app is a CLI application even when the LLM layout design omitted a
   ``cli`` file.

This file is intentionally SELF-CONTAINED: ``agentlib`` must never import
from ``behavior_tests`` (which already imports from ``agentlib``). The
intention-extraction logic here is a distinct copy that lives in the
``agentlib`` package, so the generation pipeline can use it directly.
"""

from __future__ import annotations

import re

from agentlib.config import LLM_MAX_TOKENS_LONG, LLM_RETRY_TEMPERATURE
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
        out_temp = 0.0 if _ == 0 else LLM_RETRY_TEMPERATURE
        data = _json_complete(
            messages, schema=intent_schema(), verbose=verbose,
            max_tokens=LLM_MAX_TOKENS_LONG, temperature=out_temp,
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


# --- deterministic CLI gate -------------------------------------------------

_CLI_OBSERVABLE_RE = re.compile(
    r"\b(stdout|stderr|exit|displayed|printed|shown|confirmation|"
    r"message|list|report|terminal|console|output)\b",
    re.IGNORECASE,
)

_CRUD_RE = re.compile(
    r"\b(add|create|insert|view|list|retrieve|get|show|display|fetch|"
    r"read|update|edit|modify|delete|remove|report|export|import|"
    r"calculate|search|query|submit|save|record)\b",
    re.IGNORECASE,
)


def compute_needs_cli(intentions: list[dict]) -> bool:
    """Deterministic gate: does the prompt's user intentions imply a CLI?

    The generation pipeline uses this to synthesize a command-line surface
    when the LLM layout design omitted one. Signals, strongest first:

    1. Any intention carries an explicit ``cli_command`` — the spec names the
       command line.
    2. Any intention's ``observable`` is CLI-visible (confirmation message,
       displayed list/report, stdout, exit, terminal output).
    3. Any intention's ``text`` describes a data-management capability
       (create/add/view/list/update/delete/report/export/...). For an
       entity-driven application, these are the operations a real user
       performs at the surface, so the surface is a CLI.

    Returns ``False`` when there are no intentions (or the oracle produced
    nothing), so a failed extraction degrades gracefully to no CLI — never a
    hallucinated one.
    """
    if not intentions:
        return False

    # 1. Explicit command names in the spec.
    if any((i.get("cli_command") or "").strip() for i in intentions):
        return True

    # 2. CLI-observable output.
    for i in intentions:
        obs = (i.get("observable") or "").strip()
        if obs and _CLI_OBSERVABLE_RE.search(obs):
            return True

    # 3. Data-management capability.
    return any(
        _CRUD_RE.search((i.get("text") or "").strip())
        for i in intentions
    )
