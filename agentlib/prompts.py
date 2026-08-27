"""Prompt discovery and raw source-manipulation helpers.

Extracted from agent.py. These are pure, side-effect-light utilities used by
both the LLM layer and the orchestrator.
"""
import re
from pathlib import Path

from .config import PROMPTS_DIR


def _normalise_prompt_name(raw):
    name = Path(raw).stem
    name = re.sub(r"^prompt_", "", name)
    return name


def discover_prompts():
    prompts = {}
    if PROMPTS_DIR.is_dir():
        for p in sorted(PROMPTS_DIR.glob("*.txt")):
            prompts[_normalise_prompt_name(p)] = p
    return prompts


def read_prompt(path):
    return path.read_text(encoding="utf-8").strip()


def _extract_code_block(text):
    m = re.match(r"^```(?:python)?\s*\n(.*?)\n```\s*$", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```(?:python)?\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text


def _split_multifile(code):
    marker = re.compile(r"(?:^|\n)\s*#\s*===\s*file:\s*(.+?)\s*===\s*\n", re.IGNORECASE)
    parts = marker.split(code)
    if len(parts) <= 1:
        return {"main.py": code}
    files = {}
    for i in range(1, len(parts), 2):
        filepath = parts[i].strip()
        file_content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        files[filepath] = file_content
    return files


def _output_name_for_prompt(prompt_name):
    return prompt_name.replace(" ", "_").lower()


def _join_files(files):
    """Re-join a dict of files into one code block (inverse of _split_multifile)."""
    if len(files) <= 1:
        return next(iter(files.values()), "")
    parts = []
    for name, content in files.items():
        parts.append("# === file: %s ===\n%s" % (name, content))
    return "\n\n".join(parts)
