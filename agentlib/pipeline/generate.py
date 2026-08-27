"""Deterministic generation orchestration helpers.

These functions drive free-text code generation against the local LLM and
the AST-validated retry loop, plus the per-file generation used by the
manifest-first pipeline. They are pure orchestration: every lower-level
LLM call and AST gate lives in ``agentlib.llm`` / ``agentlib.checks``.
"""

import subprocess
from pathlib import Path
from textwrap import dedent

from agentlib.config import SYSTEM_CONTEXT, LLM_MAX_TOKENS_LONG
from agentlib.llm.client import _chat_completion
from agentlib.prompts import _extract_code_block, _split_multifile, _join_files
from agentlib.checks.ast_utils import _check_syntax_and_imports, _extract_defined_names


def _run_ruff_fix(project_dir):
    """Run ruff --fix on the generated project directory."""
    try:
        subprocess.run(
            ["ruff", "check", "--fix", "--select", "E,F,I,W", str(project_dir)],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass  # ruff not available or timed out


# ---------------------------------------------------------------------------
# Code generation
# ---------------------------------------------------------------------------

def generate_code(prompt_text):
    """Free-text generation against the local OpenAI-compatible server."""
    messages = [
        {"role": "system", "content": SYSTEM_CONTEXT},
        {"role": "user", "content": prompt_text},
    ]
    return _chat_completion(messages, max_tokens=LLM_MAX_TOKENS_LONG).strip()


def generate_with_validation(prompt_text, spec_text="", sibling_exports=None,
                             verbose=False, max_retries=3):
    """Generate code with AST validation and retry."""
    last_result = None
    for attempt in range(max_retries):
        raw = generate_code(prompt_text)
        code = _extract_code_block(raw)
        last_result = code

        files = _split_multifile(code)
        errors, fixes = _check_syntax_and_imports(files, sibling_exports)

        for fp, fixed_content in fixes.items():
            files[fp] = fixed_content
            code = _join_files(files)

        real_errors = [e for e in errors if "SYNTAX" in e or "not found" in e or "nonexistent" in e]

        if not real_errors:
            if verbose and attempt > 0:
                print("      V Fixed on attempt %d" % (attempt + 1))
            return code

        if verbose:
            print("      X Attempt %d: %s" % (attempt + 1, real_errors[0]))

        if attempt < max_retries - 1:
            prompt_text = (
                prompt_text
                + "\n\nFIX THESE ERRORS:\n"
                + "\n".join("  - %s" % e for e in real_errors)
                + "\n\nReturn ONLY the corrected raw Python source code."
            )

    return last_result


def _generate_file(file_spec, manifest, prompt_text, prior_files,
                   verbose=False, db_file="app.db"):
    file_name = file_spec["file"]
    file_role = file_spec.get("role", "")
    imports_from = file_spec.get("imports_from", [])

    dep_lines = []
    for dep_name in imports_from:
        for spec in manifest:
            if Path(spec["file"]).stem == dep_name and dep_name in prior_files:
                exports = _extract_defined_names(prior_files[dep_name])
                if exports:
                    dep_lines.append(
                        "  %s.py exports: %s" % (dep_name, ", ".join(sorted(exports)))
                    )
    dep_context = "\n".join(dep_lines) if dep_lines else "  (none)"

    all_stems = {Path(s["file"]).stem: s["file"] for s in manifest}
    allowed = [s for s in imports_from if s in all_stems]
    import_map = "\n".join(
        '  from %s import <Name>  (from "%s")' % (stem, all_stems[stem])
        for stem in allowed
    ) if allowed else "  (none)"

    file_prompt = dedent("""\
        Generate file `%s`. Role: %s
        SIBLING MODULES (import from these):
        %s
        ALLOWED IMPORTS:
        %s
        RULES:
        - Use the exact class/method names, argument order, and argument
          types from the project design (never invent new ones).
        - Import ONLY the names listed above.
        - Do NOT invent module or function names.
        - Use stdlib sqlite3. No sqlalchemy.
        - The SQLite database filename is "%s" — use exactly this
          name wherever the project opens its database.
        - IDs are Optional[int] (default None).
        - Return ONLY raw Python source code.
    """) % (file_name, file_role, dep_context, import_map, db_file)

    sibling_exports = {}
    for name, content in prior_files.items():
        sibling_exports[Path(name).stem] = _extract_defined_names(content)

    code = generate_with_validation(
        file_prompt, prompt_text,
        sibling_exports=sibling_exports,
        verbose=verbose, max_retries=3,
    )
    return code, "ok" if code else "generation returned None"
