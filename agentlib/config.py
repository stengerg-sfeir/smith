"""Shared configuration constants for the neurosymbolic agent.

Moved out of agent.py so LLM, kernel, checks, and generation modules can
import these without creating import cycles.
"""
import os
from pathlib import Path
from textwrap import dedent

# Project root is two levels up from this file: agentlib/config.py
_ROOT = Path(__file__).resolve().parent.parent

PROMPTS_DIR = _ROOT / "prompts"
OUTPUT_DIR = _ROOT / "generated"

SYSTEM_CONTEXT = dedent("""\
    Expert Python engineer. Complete, runnable code.
    Rules: type hints, PEP 8, sqlite3 for DB, click for CLI.
    IDs = Optional[int], money = cents (int).
    No import *, no markdown, no commentary. Return raw code.
""")

# Local llama-server (symserver) OpenAI-compatible endpoint.
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8000/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
# Cap for LONG free-text decodes (whole-file generation / skeleton fills).
# A fill that hits the cap is truncated -> fails validation -> burns a
# retry with a different context: a major hidden run-to-run variance
# source. Keep it well above the largest expected file.
LLM_MAX_TOKENS_LONG = int(os.environ.get("LLM_MAX_TOKENS_LONG", "8192"))
# Deterministic sampling is owned by the CLIENT (not server.sh). The PRIMARY
# attempt uses temp=0 + seed=42 for reproducibility; RETRY attempts raise
# temperature so the model explores a different sample instead of re-landing
# on the same greedy output (the "identical error on retry" failure mode).
LLM_SEED = int(os.environ.get("LLM_SEED", "42"))
LLM_RETRY_TEMPERATURE = float(os.environ.get("LLM_RETRY_TEMPERATURE", "0.7"))
