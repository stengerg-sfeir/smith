"""Pass orchestration and the CLI entry point.

``_multi_pass`` drives the strict manifest-first pipeline with a
deterministic finalize phase, ``_single_pass`` is the script/tool
generator for entity-less specs, and ``process_prompt`` / ``main``
wire everything to the CLI.
"""

import argparse
import re
import sys
from pathlib import Path
from textwrap import dedent

from agentlib.config import OUTPUT_DIR
from agentlib.pipeline.manifest import _NoEntityScript, _manifest_first_blocks
from agentlib.pipeline.generate import (
    generate_code,
    generate_with_validation,
    _run_ruff_fix,
)
from agentlib.prompts import (
    read_prompt,
    _extract_code_block,
    _output_name_for_prompt,
    _split_multifile,
    discover_prompts,
    _normalise_prompt_name,
)
from agentlib.design import _route_mode
from agentlib.checks.ast_utils import (
    _extract_model_ast,
    _check_syntax_and_imports,
    _check_structural,
    _extract_defined_names,
)
from agentlib.naming import _generate_database_file


def _restore_service_signatures(files, design_ctx, verbose=False):
    """Re-impose the designed service method signatures after LLM repair.

    The multi-pass repair rewrites a service file to fix import/structural
    errors, and the small model can drop CLI-derived params (e.g.
    add_customer(name, email) instead of the designed
    add_customer(name, email, phone)) — the service↔CLI option-diffusion
    bug. The service signatures are a design contract; restore them
    deterministically so the CLI options resolve at runtime.
    """
    import ast as _ast

    from agentlib.generation.helpers import _method_stub_code

    svc_file = design_ctx.get("service_file")
    svc_design = design_ctx.get("service_design")
    if not svc_file or not svc_design or svc_file not in files:
        return
    content = files[svc_file]
    try:
        tree = _ast.parse(content)
    except SyntaxError:
        return
    fn_nodes = {
        n.name: n
        for n in _ast.walk(tree)
        if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))
    }
    lines = content.split("\n")
    # Class-body indentation: the repair can pull methods out of the class
    # (column 0); restored methods must go back INSIDE the class body.
    class_indent = 4
    for node in tree.body:
        if isinstance(node, _ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    class_indent = sub.col_offset
                    break
            break
    replacements = []
    for m in svc_design.get("methods") or []:
        name = m.get("name")
        if not name or name not in fn_nodes:
            continue
        fn = fn_nodes[name]
        expected = _method_stub_code(m, indent=0, safe_body=True)
        expected_def = expected.split("\n")[0].rstrip()
        lineno = fn.lineno
        if lineno < 1 or lineno > len(lines):
            continue
        actual = lines[lineno - 1]
        if not actual.lstrip().startswith("def %s(" % name):
            continue
        # Re-impose the class-body indentation AND the design signature.
        # Skip only when BOTH are already correct — the repair may have left
        # a matching signature but pulled the method out to column 0.
        if actual.lstrip() == expected_def and actual[: class_indent] == " " * class_indent:
            continue
        replacements.append((lineno - 1, lineno - 1, " " * class_indent + expected_def))
    if replacements:
        for s, e, new in sorted(replacements, reverse=True):
            lines[s:e + 1] = [new]
        files[svc_file] = "\n".join(lines)
        if verbose:
            print("    [restore] re-imposed %d service signature(s) from design"
                  % len(replacements))


def _multi_pass(prompt_text, verbose=False):
    """Manifest-first generation with a deterministic finalize phase.

    1. _manifest_first_blocks: schema-constrained design -> deterministic
       render -> LLM-fill of only non-contract bodies.
    2. Finalize (zero-LLM-cost where possible): AST import validation,
       structural validation, targeted LLM repair with error accumulation
       (contracts.md accumulate_errors pattern), then a deterministic
       database.py generated from the final model AST.

    Strict pipeline: there is no fallback. If the manifest-first generation
    fails, we raise so the prompt is reported as failed instead of silently
    degrading to the removed legacy multi-pass / single-pass paths (which
    let the 4B model write full file bodies and hallucinate).
    """
    try:
        files, design_ctx = _manifest_first_blocks(
            prompt_text, verbose=verbose
        )
    except _NoEntityScript:
        # Script-like project (no data entities designed): the entity-
        # driven multi-pass cannot serve it. Single-pass is the honest
        # generator for a one-file script/tool — not a legacy fallback,
        # but the correct route for this shape.
        if verbose:
            print("    No data entities — single-pass script generation")
        return _single_pass(prompt_text, verbose=verbose)
    if not files:
        raise RuntimeError(
            "manifest-first pipeline failed for this prompt "
            "(legacy fallback paths have been removed)"
        )

    # ---- Phase 4 (early): deterministic database.py from the model AST ----
    # Generate BEFORE validation so `from database import Database` resolves
    # and the table-structure check passes. Prevents the LLM repair loop from
    # firing on a clean deterministic output (the 4B model would rewrite good
    # files and reintroduce hallucinated code).
    model_classes = _extract_model_ast(files, paths=design_ctx.get("model_files"))
    if model_classes:
        files["database.py"] = _generate_database_file(
            model_classes, design_ctx.get("db_file", "app.db")
        )
        if verbose:
            print("    Generated database.py from model AST (%d tables)"
                  % len(model_classes))

    # ---- Finalize phase (deterministic AST checks) ----
    all_exports = {Path(f).stem: _extract_defined_names(c) for f, c in files.items()}
    ast_errors, ast_fixes = _check_syntax_and_imports(files, all_exports)
    for fp, fixed in ast_fixes.items():
        files[fp] = fixed

    struct_errors = _check_structural(files, design_ctx)
    all_errors = ast_errors + struct_errors
    if all_errors and verbose:
        print("    Validation: %d issue(s)" % len(all_errors))
        for err in all_errors[:5]:
            print("      - %s" % err)

    # ---- LLM repair with per-file error accumulation (targeted) ----
    repair_history = {}
    for repair_attempt in range(3):
        if not all_errors:
            break
        files_to_fix = {}
        for err in all_errors:
            for fp in files:
                if fp in err:
                    files_to_fix.setdefault(fp, []).append(err)
        if not files_to_fix:
            break
        if verbose:
            print("    Repair %d: %s"
                  % (repair_attempt + 1, ", ".join(sorted(files_to_fix))))

        for fp, errs in files_to_fix.items():
            file_content = files[fp]
            seen = set(repair_history.get(fp, []))
            for e in errs:
                if e not in seen:
                    repair_history.setdefault(fp, []).append(e)
                    seen.add(e)
            err_list = repair_history[fp][-6:]
            repair_prompt = dedent("""\
                Fix errors in this Python file.

                ERRORS (from all failed attempts — do NOT reintroduce any):
                %s

                FILE (%s):
                %s
                Return ONLY the corrected raw Python source code.
            """) % (
                "\n".join("  - %s" % e for e in err_list),
                fp,
                file_content[:3000],
            )
            raw = generate_code(repair_prompt)
            repaired = _extract_code_block(raw)
            if repaired and len(repaired) > len(file_content) * 0.3:
                files[fp] = repaired
                if verbose:
                    print("      Repaired %s" % fp)

        all_exports = {Path(f).stem: _extract_defined_names(c) for f, c in files.items()}
        ast_errors, ast_fixes = _check_syntax_and_imports(files, all_exports)
        for fp, fixed in ast_fixes.items():
            files[fp] = fixed
        struct_errors = _check_structural(files, design_ctx)
        all_errors = ast_errors + struct_errors
        if verbose and all_errors:
            print("    After repair: %d remaining" % len(all_errors))

    # The pipeline is strict by design: import-level errors that survive
    # three targeted repairs mean broken inter-file wiring (a nonexistent
    # sibling module or a missing name) that no downstream gate can undo.
    # Shipping such a tree silently is how prompt-30-style corruption used
    # to reach disk; fail loudly instead.
    if ast_errors:
        raise RuntimeError(
            "unresolved import-level errors after repair: %s"
            % "; ".join(ast_errors[:4])
        )

    # ---- Restore designed service signatures (repair may drop CLI params) ----
    _restore_service_signatures(files, design_ctx, verbose)

    # ---- Phase 4: deterministic database.py from the final model AST ----
    model_classes = _extract_model_ast(files, paths=design_ctx.get("model_files"))
    if model_classes:
        files["database.py"] = _generate_database_file(
            model_classes, design_ctx.get("db_file", "app.db")
        )
        if verbose:
            print("    Generated database.py from model AST (%d tables)"
                  % len(model_classes))

    return files


# ---------------------------------------------------------------------------
# Single-pass generation
# ---------------------------------------------------------------------------

def _single_pass(prompt_text, verbose=False):
    full_prompt = dedent("""\
        %s
        Return ONLY raw Python source code -- no markdown, no commentary.
        For multi-file projects: # === file: path/to/file.py ===
    """) % prompt_text

    code = generate_with_validation(
        full_prompt, prompt_text,
        verbose=verbose, max_retries=3,
    )
    return _split_multifile(code or "")


# ---------------------------------------------------------------------------
# Fix relative imports
# ---------------------------------------------------------------------------

def _fix_relative_imports(files, verbose=False):
    fixed = {}
    for filepath, content in files.items():
        new_content = re.sub(r"from \.(\w+)", r"from \1", content)
        if new_content != content and verbose:
            print("    Fixed relative imports in %s" % filepath)
        fixed[filepath] = new_content
    return fixed


# ---------------------------------------------------------------------------
# Main workflow
# ---------------------------------------------------------------------------

def process_prompt(prompt_name, prompt_path, verbose=True):
    if verbose:
        print("\n" + "=" * 60)
        print("  Prompt : %s" % prompt_name)
        print("  Source : %s" % prompt_path)
        print("=" * 60)

    prompt_text = read_prompt(prompt_path)
    if verbose:
        print("\n--- Prompt ---\n%s\n--------------\n" % prompt_text)
        print("Generating code ...")

    mode = _route_mode(prompt_text, verbose=verbose)
    if verbose:
        print("  Mode: %s-pass" % mode)
    if mode == "multi":
        files = _multi_pass(prompt_text, verbose=verbose)
    else:
        files = _single_pass(prompt_text, verbose=verbose)

    if len(files) > 1:
        files = _fix_relative_imports(files, verbose=verbose)

    project_dir = OUTPUT_DIR / _output_name_for_prompt(prompt_name)
    project_dir.mkdir(parents=True, exist_ok=True)

    # Stale artifacts from a previous run of THIS prompt must not survive:
    # a file declared in an earlier manifest but absent from the regenerated
    # set would otherwise linger as a dead/empty module (observed with the
    # repository interface/implementation split for prompt 30). Remove any
    # top-level .py file not in the new file set before writing.
    for existing in project_dir.iterdir():
        if (
            existing.is_file()
            and existing.name not in files
            and existing.name.endswith(".py")
        ):
            existing.unlink()

    # LAST-RESORT entry-point guarantee: the LLM repair loop above rewrites a
    # cli.py with a syntax error and drops the `if __name__ == "__main__":
    # cli()` block, leaving every CLI command a silent no-op (library_system
    # __seed_Loan FK failure was traced to exactly this). Re-assert the
    # dispatch on the FINAL output so the CLI is always invocable.
    for fn, content in list(files.items()):
        if Path(fn).stem == "cli" and "if __name__" not in content:
            files[fn] = content.rstrip() + "\n\nif __name__ == \"__main__\":\n    cli()\n"

    for rel_path, content in files.items():
        target = project_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + "\n", encoding="utf-8")
        if verbose:
            print("  wrote %s" % target.relative_to(Path.cwd()))

    # Run ruff --fix for style cleanup
    if len(files) > 1:
        _run_ruff_fix(project_dir)

    if verbose:
        print("\n  Project written to %s/\n" % project_dir.relative_to(Path.cwd()))
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Neurosymbolic Python Coding Agent")
    parser.add_argument("--prompt", "-p", help="Process a single prompt by name.")
    parser.add_argument("--list", "-l", action="store_true", help="List available prompts.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress verbose output.")
    args = parser.parse_args()

    prompts = discover_prompts()
    if not prompts:
        print("No prompts found in prompts/", file=sys.stderr)
        sys.exit(1)

    if args.list:
        print("Available prompts:")
        for name, path in prompts.items():
            print("  %-25s (%s)" % (name, path.name))
        sys.exit(0)

    if args.prompt:
        key = _normalise_prompt_name(args.prompt)
        matches = [k for k in prompts if key in k]
        if not matches:
            print("No prompt matching '%s'. Available: %s" % (args.prompt, ", ".join(prompts)), file=sys.stderr)
            sys.exit(1)
        targets = {m: prompts[m] for m in matches}
    else:
        targets = prompts

    verbose = not args.quiet
    succeeded, failed = 0, 0

    for name, path in targets.items():
        try:
            if process_prompt(name, path, verbose=verbose):
                succeeded += 1
        except Exception as exc:
            import traceback
            traceback.print_exc(file=sys.stderr)
            print("  FAILED: %s" % exc, file=sys.stderr)
            failed += 1

    print("\nDone -- %d succeeded, %d failed out of %d prompt(s)." % (succeeded, failed, len(targets)))
    sys.exit(0 if failed == 0 else 1)
