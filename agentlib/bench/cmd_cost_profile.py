#!/usr/bin/env python3
"""Generation cost profile: where the wall time of a prompt actually goes.

Measures the generator's LLM cost per PHASE, not just per project. Every
completion in the pipeline funnels through one function,
`agentlib.llm.client._chat_completion`; this harness wraps it, records each
call's duration / input+output size / tokens reported by the server / immediate
caller, then prints the attribution. `_json_complete` resolves that name as a
module global at call time and `agentlib.llm.fill` / `agentlib.pipeline.generate`
import it by name, so every importing namespace is patched in place — no call
can bypass the counter.

Three units are recorded, because they answer different questions and only one
of them is available everywhere:

* **seconds** — the cost that is actually paid;
* **chars** — the traffic, always measurable, on every call, streamed or not;
* **tokens** — what the server itself counted (`usage`), which llama.cpp
  reports on the schema-constrained JSON calls and omits on the streamed code
  fills. The report counts how many calls reported tokens so a total is never
  read as if it covered all of them.

`--json PATH` writes the same numbers as an artifact, which is what makes the
comparison in `analysis/claude_vs_generator.md` reproducible instead of copied.

Usage:
    python3 bench.py cost --prompt library_system --prompt expenses
    python3 bench.py cost --prompt expenses --json analysis/generation_cost_profile.json
"""
import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

# The repository root: this module lives in agentlib/bench/.
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_call_log = []


def _caller_chain(max_frames=3):
    """Names of the first frames OUTSIDE the plumbing that reached the client.

    Both this harness and `agentlib.llm.client` are skipped. The client matters
    as much as the harness here: the frame just above `_chat_completion` is
    always `client.py:_json_complete`, so keeping it would label every call site
    `client.py:_json_complete` and hide the phase this harness exists to
    attribute (`design.py:_design_module`, `method_contract.py:…`, …). The two
    files are compared by ABSOLUTE PATH, not by basename: a generated project
    that happens to ship its own `client.py` must not be mistaken for the
    plumbing.
    """
    import agentlib.llm.client as client

    plumbing = {os.path.abspath(__file__), os.path.abspath(client.__file__)}
    frames = []
    for frame in reversed(traceback.extract_stack()[:-1]):
        if os.path.abspath(frame.filename) in plumbing:
            continue
        frames.append("%s:%s" % (os.path.basename(frame.filename), frame.name))
        if len(frames) == max_frames:
            break
    return " < ".join(frames)


# The unpatched client function and the ONE wrapper built around it. Both are
# set once, at the first install, and never stacked — see `_install_counter`.
_ORIGINAL = None
_WRAPPER = None


def _make_wrapper(original):
    """The counting wrapper: exactly one level of bookkeeping around `original`."""
    import agentlib.llm.client as client

    def counted(messages, **kwargs):
        caller = _caller_chain()
        started = time.time()
        try:
            output = original(messages, **kwargs)
        except BaseException:
            _call_log.append(
                _record(caller, time.time() - started, messages, "",
                        error=True, usage=client.LAST_USAGE)
            )
            raise
        # Read AFTER the call, from the client itself: the wrapper must report
        # what the server said, not what the caller hoped it said.
        _call_log.append(
            _record(caller, time.time() - started, messages, output or "",
                    usage=client.LAST_USAGE)
        )
        return output

    return counted


def _install_counter():
    """Wrap `_chat_completion` in every namespace that imported it.

    Idempotent BY CONSTRUCTION: the true function is captured once and a single
    wrapper is built once, so calling this once per prompt cannot stack two
    layers. Stacking is not hypothetical — it is how a six-prompt run reported
    `expenses` consuming exactly six times its real traffic, with its "LLM
    seconds" six times its own wall clock. Every number this harness publishes
    is meaningful only because the depth here is exactly one.
    """
    global _ORIGINAL, _WRAPPER
    import agentlib.llm.client as client

    if _ORIGINAL is None:
        _ORIGINAL = client._chat_completion
    if _WRAPPER is None:
        _WRAPPER = _make_wrapper(_ORIGINAL)

    patched = []
    for module in list(sys.modules.values()):
        if module is None or not hasattr(module, "_chat_completion"):
            continue
        # `client` itself, every `from ..client import _chat_completion` site,
        # and a namespace already holding the wrapper: all of them must end up
        # pointing at the SAME single wrapper.
        if getattr(module, "_chat_completion") in (_ORIGINAL, _WRAPPER):
            setattr(module, "_chat_completion", _WRAPPER)
            patched.append(getattr(module, "__name__", "?"))
    return patched


def _usage_tokens(usage):
    """`(prompt_tokens, completion_tokens)` of one call, or `(0, 0)`.

    A streamed completion carries no `usage` in this client, so zeros here mean
    "not reported" and are counted separately rather than silently summed as
    if the call had cost nothing.
    """
    if not isinstance(usage, dict):
        return 0, 0
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return (
        prompt if isinstance(prompt, int) else 0,
        completion if isinstance(completion, int) else 0,
    )


def _record(caller, seconds, messages, output, error=False, usage=None):
    tokens_in, tokens_out = _usage_tokens(usage)
    return {
        "caller": caller,
        "seconds": seconds,
        "chars_in": sum(len(m.get("content") or "") for m in messages),
        "chars_out": len(output or ""),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "tokens_reported": isinstance(usage, dict),
        "error": error,
    }


def _top_caller(entry):
    return entry["caller"].split(" < ")[0]


def _source_metrics(project_dir):
    """Size of the project the generator wrote — the DELIVERABLE, not the traffic.

    This is the one number that is directly comparable with the Claude
    baseline: both sides measure the source they shipped, from the bytes on
    disk, without asking either model to report its own size.
    """
    if not project_dir.is_dir():
        return {"source_files": 0, "source_chars": 0}
    files = [
        path for path in sorted(project_dir.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]
    chars = 0
    for path in files:
        chars += len(path.read_text(encoding="utf-8", errors="replace"))
    return {"source_files": len(files), "source_chars": chars}


def _totals(entries):
    return {
        "calls": len(entries),
        "seconds": sum(e["seconds"] for e in entries),
        "chars_in": sum(e["chars_in"] for e in entries),
        "chars_out": sum(e["chars_out"] for e in entries),
        "tokens_in": sum(e["tokens_in"] for e in entries),
        "tokens_out": sum(e["tokens_out"] for e in entries),
        "tokens_calls": sum(1 for e in entries if e["tokens_reported"]),
        "errors": sum(1 for e in entries if e["error"]),
    }


def _print_report(ident, patched, wall_seconds, source):
    total = _totals(_call_log)
    llm_seconds = total["seconds"]
    chars_out = total["chars_out"]

    print("\n=== %s ===" % ident)
    print("patched modules      : %s" % ", ".join(patched))
    print("wall seconds         : %.1f" % wall_seconds)
    print("LLM seconds          : %.1f (%.0f%% of wall)"
          % (llm_seconds, 100.0 * llm_seconds / wall_seconds if wall_seconds else 0))
    print("calls / output chars : %d / %d" % (total["calls"], chars_out))
    print("input chars          : %d" % total["chars_in"])
    print("tokens in / out      : %d / %d (on %d of %d calls)"
          % (total["tokens_in"], total["tokens_out"],
             total["tokens_calls"], total["calls"]))
    if chars_out:
        print("ms per output char   : %.2f" % (1000.0 * llm_seconds / chars_out))
    print("errors               : %d" % total["errors"])
    print("source written       : %d files / %d chars"
          % (source["source_files"], source["source_chars"]))

    by_phase = {}
    for entry in _call_log:
        bucket = by_phase.setdefault(
            _top_caller(entry),
            {"calls": 0, "seconds": 0.0, "chars_out": 0, "tokens_in": 0,
             "tokens_out": 0},
        )
        bucket["calls"] += 1
        bucket["seconds"] += entry["seconds"]
        bucket["chars_out"] += entry["chars_out"]
        bucket["tokens_in"] += entry["tokens_in"]
        bucket["tokens_out"] += entry["tokens_out"]
    print("by phase (caller of _chat_completion):")
    for name, bucket in sorted(by_phase.items(), key=lambda kv: -kv[1]["seconds"]):
        print("  %-34s calls=%-3d llm=%7.1fs out=%7d tok=%7d/%7d"
              % (name, bucket["calls"], bucket["seconds"], bucket["chars_out"],
                 bucket["tokens_in"], bucket["tokens_out"]))

    print("slowest calls:")
    for entry in sorted(_call_log, key=lambda e: -e["seconds"])[:6]:
        print("  %6.1fs  out=%6d  in=%6d  %s"
              % (entry["seconds"], entry["chars_out"], entry["chars_in"],
                 entry["caller"]))
    profile = {
        "ident": ident,
        "wall_seconds": max(wall_seconds, 0.0),
        "llm_seconds": llm_seconds,
        "calls": total["calls"],
        "chars_in": total["chars_in"],
        "chars_out": total["chars_out"],
        "tokens_in": total["tokens_in"],
        "tokens_out": total["tokens_out"],
        "tokens_calls": total["tokens_calls"],
        "errors": total["errors"],
        "by_phase": by_phase,
        "slowest": sorted(
            (
                {"caller": e["caller"], "seconds": e["seconds"],
                 "chars_in": e["chars_in"], "chars_out": e["chars_out"],
                 "tokens_in": e["tokens_in"], "tokens_out": e["tokens_out"]}
                for e in _call_log
            ),
            key=lambda e: -e["seconds"],
        )[:6],
    }
    profile.update(source)
    return profile


def profile_prompt(ident):
    """Run the real pipeline entry point for one prompt and report its cost."""
    from agentlib.config import OUTPUT_DIR
    from agentlib.prompts import _output_name_for_prompt
    import agentlib.pipeline.run as run

    _call_log.clear()
    patched = _install_counter()
    prompt_path = PROMPTS_DIR / ("prompt_%s.txt" % ident)
    if not prompt_path.exists():
        raise SystemExit("no such prompt file: %s" % prompt_path)
    started = time.time()
    run.process_prompt(ident, prompt_path, verbose=False)
    wall_seconds = time.time() - started
    # The SAME path `process_prompt` resolved, through the same helper, so the
    # source measured is the source the pipeline actually wrote.
    project_dir = OUTPUT_DIR / _output_name_for_prompt(ident)
    return _print_report(ident, patched, wall_seconds, _source_metrics(project_dir))


def _write_json(path, profiles):
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator_model": "Qwen3-4B-Instruct-2507-Q4_K_M",
        "unit_note": (
            "chars are measured on every call; tokens are what llama-server "
            "reported in `usage` (the schema-constrained JSON calls), so "
            "tokens_calls < calls leaves part of the output measured in chars "
            "only — see README of the harness for why the streamed fills carry "
            "no usage."
        ),
        "prompts": profiles,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\njson -> %s" % target)


def _failed_profile(ident, exc):
    """A profile-shaped record for a prompt whose generation RAISED.

    Batch isolation: a prompt that crashes the generator (34's unresolved
    import, 18's null-fill TypeError) must be reported as ONE failed prompt
    and must NOT abort the rest of the lot. The record carries every key the
    summary and the JSON writer read, so a failed run still produces a
    complete, comparable artefact instead of no file at all.
    """
    return {
        "ident": ident,
        "wall_seconds": 0.0,
        "llm_seconds": 0.0,
        "calls": 0,
        "chars_in": 0,
        "chars_out": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "tokens_calls": 0,
        "errors": 1,
        "failed": True,
        "failure": "%s: %s" % (type(exc).__name__, exc),
        "by_phase": {},
        "slowest": [],
        "source_files": 0,
        "source_chars": 0,
    }


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", action="append", required=True,
                        help="prompt ident, repeatable (e.g. --prompt expenses)")
    parser.add_argument("--json", default=None, metavar="PATH",
                        help="also write the per-prompt numbers as JSON")
    args = parser.parse_args(argv)
    profiles = []
    for ident in args.prompt:
        # SystemExit is caught alongside Exception on purpose: a missing
        # prompt file is reported with `raise SystemExit(...)` inside
        # `profile_prompt`, and SystemExit derives from BaseException, so an
        # `except Exception` would let it end the whole batch (measured:
        # `--prompt zzz_nonexistent` printed the message and shipped no
        # summary at all). KeyboardInterrupt is deliberately NOT caught, so
        # Ctrl-C still stops the run.
        try:
            profiles.append(profile_prompt(ident))
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - batch isolation
            # One prompt's failure must never cancel the prompts after it:
            # record it and keep going, so the batch and its JSON are always
            # complete (this is how 18's crash used to take 19/20 down).
            print("\n=== %s ===" % ident)
            print("  FAILED: %s: %s" % (type(exc).__name__, exc))
            profiles.append(_failed_profile(ident, exc))

    print("\n=== summary ===")
    for profile in profiles:
        print("  %-16s wall=%6.1fs  llm=%6.1fs  calls=%-3d out=%7d tok=%7d/%7d src=%6d"
              % (profile["ident"], profile["wall_seconds"], profile["llm_seconds"],
                 profile["calls"], profile["chars_out"], profile["tokens_in"],
                 profile["tokens_out"], profile["source_chars"]))
    if args.json:
        _write_json(args.json, profiles)


if __name__ == "__main__":
    main()
