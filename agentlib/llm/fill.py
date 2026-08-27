"""LLM body-filling for service / repository custom methods.

Extracted from agent.py. A fill is one constrained streamed completion that
re-emits the whole file with the locked skeleton's signatures preserved;
it is only accepted if it compiles.
"""
from ..config import LLM_MAX_TOKENS_LONG
from ..prompts import _extract_code_block
from .client import _StreamLimitExceeded, _chat_completion


def _compiles(text):
    try:
        compile(text, "<llm>", "exec")
        return True
    except SyntaxError:
        return False


def _llm_fill(path, instruction, skeleton, prompt_text, verbose=False):
    """One LLM call: fill skeleton bodies, keep signatures/imports exact.

    Returns the full file text or None. Two attempts with corrective retry
    on compile failure.
    """
    user = instruction + "\n\nSKELETON:\n```python\n" + skeleton + "\n```"
    messages = [
        {
            "role": "system",
            "content": (
                "You are a meticulous senior Python engineer. You produce "
                "complete, runnable, dependency-correct code and you NEVER "
                "change signatures, class names, or imports you are told to keep."
            ),
        },
        {"role": "user", "content": user},
    ]
    # Sanity bound on a legit fill output: repo fills re-emit the whole file
    # (~skeleton size); service fills re-emit the full service (~4x the mini
    # skeleton). 2x with a 10k floor leaves headroom for real files while
    # catching degenerate repetition loops that otherwise decode to
    # max_tokens (observed: 6250+ tokens for a ~1900-token repo fill).
    max_output_chars = max(len(skeleton) * 2, 10000)
    for attempt in range(2):
        try:
            raw = _chat_completion(
                messages, max_tokens=LLM_MAX_TOKENS_LONG,
                stream=True, max_output_chars=max_output_chars,
            )
        except _StreamLimitExceeded:
            if verbose:
                print("    [fill] %s: output runaway — stream aborted (attempt %d)"
                      % (path, attempt + 1))
            raw = None
        body = _extract_code_block(raw) if raw else None
        if body and _compiles(body):
            return body + "\n"
        if verbose and raw is not None:
            print("    [fill] %s: output rejected (attempt %d)" % (path, attempt + 1))
        # No-accumulate retry: rebuild the conversation fresh so the prompt
        # never grows with the model's own (large) previous output — retry
        # prompts used to balloon to ~6k tokens and blow past the call
        # timeout. Only a short correction note is added.
        messages = [
            messages[0],
            {
                "role": "user",
                "content": user
                + "\n\nYour previous output was rejected because it did not "
                "compile or preserve the locked structure. Re-emit the COMPLETE "
                "corrected file in a single ```python ... ``` block, keeping "
                "every class name, method signature and import line exactly as "
                "in the skeleton.",
            },
        ]
    return None
