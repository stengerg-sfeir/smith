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

from agentlib.config import OUTPUT_DIR, LLM_RETRY_TEMPERATURE
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
from agentlib.generation.annotations import add_missing_none_returns
from agentlib.generation.cli_wiring import fix_click_option_params
from agentlib.generation.entrypoint import ensure_entry_point
from agentlib.generation.ownership_guard import (
    apply_ownership_cli,
    apply_ownership_guards,
)
from agentlib.generation.role_guard import apply_role_cli, apply_role_guards
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
            attempt_temp = 0.0 if repair_attempt == 0 else LLM_RETRY_TEMPERATURE
            raw = generate_code(repair_prompt, temperature=attempt_temp)
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

    # ---- E3 + E4: ownership then role scoping, imposed LAST ----------------
    _apply_ownership_scope(files, design_ctx, verbose=verbose)
    _apply_role_scope(files, design_ctx, verbose=verbose)

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


def _apply_ownership_scope(files, design_ctx, verbose=False):
    """Impose the specification's ownership rule on the FINAL tree (E3).

    Prompt 38 scopes access to the caller's own rows:

        "Users must authenticate before accessing documents. A user can only
         read, modify or delete their own documents."

    The tree rendered for it let ANY caller list every document, and offered
    ``document update --user-id`` as a way to hand a document to somebody else.

    Imposed here, and not during the render phase, because the acting user is
    no part of the DESIGNED service contract: ``_restore_service_signatures``
    re-imposes every service method's designed signature (it exists to undo the
    repair loop's dropped CLI parameters), so a parameter added while rendering
    is deleted from the ``def`` while its guarded body stays — every guarded
    call then dies on ``NameError: user_id``. A specification requirement is
    imposed after the design contract, on what is actually shipped.
    """
    rule = design_ctx.get("ownership_rule")
    if not rule:
        return

    repo_files = [p for p in design_ctx.get("repo_files") or [] if p in files]
    repos = {p: files[p] for p in repo_files}
    for svc_path in design_ctx.get("service_files") or []:
        source = files.get(svc_path)
        if not source:
            continue
        source, repos, notes = apply_ownership_guards(
            source, repos, rule, design_ctx.get("exceptions"),
        )
        if notes:
            files[svc_path] = source
            if verbose:
                print("    [ownership] %s: %s" % (svc_path, "; ".join(notes)))
    for repo_path, repo_source in repos.items():
        files[repo_path] = repo_source

    for cli_path in design_ctx.get("cli_files") or []:
        cli_source = files.get(cli_path)
        if not cli_source:
            continue
        cli_source, notes = apply_ownership_cli(cli_source, rule)
        if notes:
            files[cli_path] = cli_source
            if verbose:
                print("    [ownership] %s: %s" % (cli_path, "; ".join(notes)))


def _apply_role_scope(files, design_ctx, verbose=False):
    """Impose the specification's role policy on the FINAL tree (E4).

    Prompt 39: "Administrators can manage products and users. Normal users can
    create orders and view their own orders but cannot modify products or other
    users."

    Like the ownership rule, this is a specification requirement rather than
    part of the designed service contract, so it is imposed after the design
    signatures have been restored (see ``_apply_ownership_scope``) — and after
    it, so the two guards never edit the same method signature twice.
    """
    rule = design_ctx.get("role_rule")
    if not rule:
        return

    repo_files = [p for p in design_ctx.get("repo_files") or [] if p in files]
    repos = {p: files[p] for p in repo_files}
    for svc_path in design_ctx.get("service_files") or []:
        source = files.get(svc_path)
        if not source:
            continue
        source, notes = apply_role_guards(
            source, rule, design_ctx.get("exceptions"), repos,
        )
        if notes:
            files[svc_path] = source
            if verbose:
                print("    [roles] %s: %s" % (svc_path, "; ".join(notes)))

    for cli_path in design_ctx.get("cli_files") or []:
        cli_source = files.get(cli_path)
        if not cli_source:
            continue
        cli_source, notes = apply_role_cli(cli_source, rule)
        if notes:
            files[cli_path] = cli_source
            if verbose:
                print("    [roles] %s: %s" % (cli_path, "; ".join(notes)))


# ---------------------------------------------------------------------------
# Single-pass generation
# ---------------------------------------------------------------------------

def _single_pass(prompt_text, verbose=False):
    full_prompt = dedent("""\
        %s
        Return ONLY raw Python source code -- no markdown, no commentary.
        For multi-file projects: # === file: path/to/file.py ===
        Every function and method annotates every parameter and its return
        type; a function that returns nothing is annotated `-> None`.
    """) % prompt_text

    code = generate_with_validation(
        full_prompt, prompt_text,
        verbose=verbose, max_retries=3,
    )
    files = _split_multifile(code or "")
    # Deterministic annotation floor: the system rule ("type hints") is only
    # a statement TO the model, and the 4B model does drop it on a trivial
    # file (`def main():`). `-> None` is the one annotation derivable
    # without guessing the author's intent, so it is imposed here.
    files, annotated = add_missing_none_returns(files)
    if verbose and annotated:
        print("    Annotated %d untyped return(s) -> None" % annotated)
    return files


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

    # Click WIRING guarantee on the FINAL output: click binds a callback's
    # parameters by the option's `dest` (the long name, dashes -> underscores),
    # so a command written `--list` with a callback parameter `list_flag`
    # raises `TypeError: cli() got an unexpected keyword argument 'list'` on
    # EVERY invocation (prompt 03). Deterministic rename of exactly the
    # parameters click cannot bind; a wired file is untouched.
    files, rewired = fix_click_option_params(files)
    if verbose and rewired:
        print("    Rewired click option parameter(s) in %d file(s)" % rewired)

    # Entry-point guarantee on the FINAL output. Two observed ways to lose
    # the dispatch: the LLM repair loop rewrites cli.py and drops its
    # `__main__` block (every command becomes a silent no-op — the
    # library_system __seed_Loan FK failure traced to exactly this), and the
    # single-pass path drops it altogether (csv_to_json.py shipped with NO
    # guard, so the whole tool did nothing and "succeeded"). One generic
    # rule re-asserts both; it never touches a file that already has one.
    files, added_guards = ensure_entry_point(files)
    if verbose and added_guards:
        print("    Added %d entry-point guard(s)" % added_guards)

    for rel_path, content in files.items():
        target = project_dir / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + "\n", encoding="utf-8")
        if verbose:
            print("  wrote %s" % target.relative_to(Path.cwd()))

    # Run ruff --fix for style cleanup on EVERY project, not only multi-file
    # ones: a single-file script is exactly where an unused import survives
    # (the "sqlite3 for DB" system rule obeyed by a project that has no
    # database) and the single-pass path has no other gate at all.
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
