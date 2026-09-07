"""LLM body-filling for service / repository custom methods.

Extracted from agent.py. A fill is one constrained streamed completion that
re-emits the whole file with the locked skeleton's signatures preserved;
it is only accepted if it compiles.
"""
from ..config import LLM_MAX_TOKENS_LONG, LLM_RETRY_TEMPERATURE
from ..prompts import _extract_code_block
from .client import _StreamLimitExceeded, _chat_completion


def _compiles(text):
    try:
        compile(text, "<llm>", "exec")
        return True
    except SyntaxError:
        return False


def _llm_fill(path, instruction, skeleton, prompt_text, verbose=False,
              temperature=0.0):
    """One LLM call: fill skeleton bodies, keep signatures/imports exact.

    Returns the full file text or None. Two attempts with corrective retry
    on compile failure. `temperature` is the sampling temperature of the
    FIRST attempt; the retry raises it to LLM_RETRY_TEMPERATURE so the
    model explores a different sample instead of re-emitting the same
    broken body.
    """
    # The original requirements are BUSINESS CONTEXT the fill needs to
    # implement domain-verb stubs correctly. Without them the model only
    # sees a bare method name + flat repo API and must guess the semantics
    # (library_system's return_loan invented Member.loan_count, and
    # get_loan_report summed a date field, because the fill never saw the
    # prompt). Pass it through as a lead-in; the locked skeleton + repo
    # interface stay authoritative, and the semantic validator still gates
    # the output. This is purely additive — deterministic contract bodies
    # never pass through here, so it cannot regress those.
    user = instruction + "\n\nSKELETON:\n```python\n" + skeleton + "\n```"
    if prompt_text:
        user = (
            "ORIGINAL REQUIREMENTS — read these to implement the business "
            "bodies below. The locked skeleton and the repository API are "
            "AUTHORITATIVE: never invent methods, fields, or models beyond "
            "what they declare.\n\n"
            + prompt_text.strip()
            + "\n\n"
            + user
        )
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
    # skeleton). The previous 2x/10k floor was too tight: a large service
    # skeleton (~5k chars) produced a legitimate ~6k-token (~24k char) fill
    # that the local stream cutoff mislabelled "output runaway" even though
    # the server completed it untruncated. 4x with a 30k floor keeps catching
    # degenerate repetition loops while leaving real large files headroom.
    max_output_chars = max(len(skeleton) * 4, 30000)
    for attempt in range(2):
        # temp=0 on the primary attempt (reproducible); a retry raises temp
        # so the model explores a different sample instead of re-emitting the
        # same broken body. A caller already on a retry passes temperature>0
        # so even this function's first attempt explores.
        attempt_temp = temperature if attempt == 0 else LLM_RETRY_TEMPERATURE
        try:
            raw = _chat_completion(
                messages, max_tokens=LLM_MAX_TOKENS_LONG,
                stream=True, max_output_chars=max_output_chars,
                temperature=attempt_temp,
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
