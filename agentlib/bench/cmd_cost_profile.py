#!/usr/bin/env python3
"""Generation cost profile: where the wall time of a prompt actually goes.

Measures the generator's LLM cost per PHASE, not just per project. Every
completion in the pipeline funnels through one function,
`agentlib.llm.client._chat_completion`; this harness wraps it, records each
call's duration / input+output size / immediate caller, then prints the
attribution. `_json_complete` resolves that name as a module global at call
time and `agentlib.llm.fill` / `agentlib.pipeline.generate` import it by name,
so every importing namespace is patched in place — no call can bypass the
counter.

Usage:
    python3 run_cost_profile.py --prompt library_system --prompt expenses
"""
import argparse
import os
import sys
import time
import traceback
from pathlib import Path

# The repository root: this module lives in agentlib/bench/.
PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"

_call_log = []


def _caller_chain(max_frames=3):
    """Names of the first non-harness frames calling into the LLM client."""
    frames = []
    for frame in reversed(traceback.extract_stack()[:-1]):
        base = os.path.basename(frame.filename)
        if base == os.path.basename(__file__):
            continue
        frames.append("%s:%s" % (base, frame.name))
        if len(frames) == max_frames:
            break
    return " < ".join(frames)


def _install_counter():
    """Wrap `_chat_completion` in every namespace that imported it."""
    import agentlib.llm.client as client

    original = client._chat_completion

    def counted(messages, **kwargs):
        caller = _caller_chain()
        started = time.time()
        try:
            output = original(messages, **kwargs)
        except BaseException:
            _call_log.append(
                _record(caller, time.time() - started, messages, "", error=True)
            )
            raise
        _call_log.append(
            _record(caller, time.time() - started, messages, output or "")
        )
        return output

    patched = []
    for module in list(sys.modules.values()):
        if module is None or not hasattr(module, "_chat_completion"):
            continue
        if getattr(module, "_chat_completion") is original:
            setattr(module, "_chat_completion", counted)
            patched.append(getattr(module, "__name__", "?"))
    return patched


def _record(caller, seconds, messages, output, error=False):
    return {
        "caller": caller,
        "seconds": seconds,
        "chars_in": sum(len(m.get("content") or "") for m in messages),
        "chars_out": len(output or ""),
        "error": error,
    }


def _top_caller(entry):
    return entry["caller"].split(" < ")[0]


def _print_report(ident, patched, wall_seconds):
    total = len(_call_log)
    llm_seconds = sum(e["seconds"] for e in _call_log)
    chars_out = sum(e["chars_out"] for e in _call_log)

    print("\n=== %s ===" % ident)
    print("patched modules      : %s" % ", ".join(patched))
    print("wall seconds         : %.1f" % wall_seconds)
    print("LLM seconds          : %.1f (%.0f%% of wall)"
          % (llm_seconds, 100.0 * llm_seconds / wall_seconds if wall_seconds else 0))
    print("calls / output chars : %d / %d" % (total, chars_out))
    if chars_out:
        print("ms per output char   : %.2f" % (1000.0 * llm_seconds / chars_out))
    print("errors               : %d" % sum(1 for e in _call_log if e["error"]))

    by_phase = {}
    for entry in _call_log:
        bucket = by_phase.setdefault(
            _top_caller(entry), {"calls": 0, "seconds": 0.0, "chars_out": 0}
        )
        bucket["calls"] += 1
        bucket["seconds"] += entry["seconds"]
        bucket["chars_out"] += entry["chars_out"]
    print("by phase (caller of _chat_completion):")
    for name, bucket in sorted(by_phase.items(), key=lambda kv: -kv[1]["seconds"]):
        print("  %-34s calls=%-3d llm=%7.1fs out=%7d"
              % (name, bucket["calls"], bucket["seconds"], bucket["chars_out"]))

    print("slowest calls:")
    for entry in sorted(_call_log, key=lambda e: -e["seconds"])[:6]:
        print("  %6.1fs  out=%6d  in=%6d  %s"
              % (entry["seconds"], entry["chars_out"], entry["chars_in"],
                 entry["caller"]))
    return {
        "ident": ident,
        "wall_seconds": wall_seconds,
        "llm_seconds": llm_seconds,
        "calls": total,
        "chars_out": chars_out,
        "by_phase": by_phase,
    }


def profile_prompt(ident):
    """Run the real pipeline entry point for one prompt and report its cost."""
    import agentlib.pipeline.run as run

    _call_log.clear()
    patched = _install_counter()
    prompt_path = PROMPTS_DIR / ("prompt_%s.txt" % ident)
    if not prompt_path.exists():
        raise SystemExit("no such prompt file: %s" % prompt_path)
    started = time.time()
    run.process_prompt(ident, prompt_path, verbose=False)
    return _print_report(ident, patched, time.time() - started)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", action="append", required=True,
                        help="prompt ident, repeatable (e.g. --prompt expenses)")
    args = parser.parse_args(argv)
    profiles = [profile_prompt(ident) for ident in args.prompt]

    print("\n=== summary ===")
    for profile in profiles:
        print("  %-16s wall=%6.1fs  llm=%6.1fs  calls=%-3d out=%7d"
              % (profile["ident"], profile["wall_seconds"], profile["llm_seconds"],
                 profile["calls"], profile["chars_out"]))


if __name__ == "__main__":
    main()
