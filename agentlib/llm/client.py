"""OpenAI-compatible llama-server client.

Extracted from agent.py so the rest of the package can use these helpers
without an import cycle. Provides schema-constrained (GBNF) JSON completion
and SSE streaming with an output cap.
"""
import json
import sys
import urllib.request

from ..config import LLM_BASE_URL, LLM_SEED, LLM_RETRY_TEMPERATURE


class _StreamLimitExceeded(Exception):
    """Raised when a streaming completion exceeds max_output_chars.

    Carries the partial output so callers can log the diagnostic and discard
    it — a truncated/degenerate decode is never returned as valid code.
    """

    def __init__(self, partial):
        self.partial = partial
        super().__init__("stream output exceeded max_output_chars")


def _chat_completion(messages, max_tokens=2048, temperature=0.0, seed=None,
                     top_p=None, schema=None, timeout=180, stream=False,
                     max_output_chars=None):
    """Call the local OpenAI-compatible llama-server.

    When `schema` is a dict, it is passed as response_format so the server
    constrains generation with a GBNF grammar — the model physically cannot
    emit malformed or out-of-schema JSON.

    When `stream` is True the request uses SSE streaming and the accumulated
    text is returned. `max_output_chars` (with stream=True) aborts early by
    raising _StreamLimitExceeded once the running output exceeds it — this
    bounds degenerate/repetition decodes that a non-streaming caller could
    only wait out until the socket timeout.
    """
    body = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    # Deterministic primary: temp=0 + fixed seed=42 so a given prompt is
    # reproducible. Retries (temp>0) omit the seed, so the server samples a
    # fresh random sequence each time — otherwise a fixed seed + temp>0 would
    # re-emit the same sample and reproduce the identical error.
    if seed is None and temperature == 0.0:
        seed = LLM_SEED
    if seed is not None:
        body["seed"] = seed
    if top_p is not None:
        body["top_p"] = top_p
    if schema is not None:
        body["response_format"] = {"type": "json_object", "schema": schema}
    if stream:
        body["stream"] = True
    req = urllib.request.Request(
        LLM_BASE_URL + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if not stream:
            data = json.loads(resp.read().decode("utf-8"))
            choice = data["choices"][0]
            if choice.get("finish_reason") == "length":
                # Truncated output: make it VISIBLE instead of letting it
                # surface later as a mysterious validation failure.
                print(
                    "    [warn] completion hit max_tokens=%d — output truncated"
                    % max_tokens,
                    file=sys.stderr,
                )
            return choice["message"]["content"]

        # ---- streaming SSE ----
        parts = []
        chars = 0
        finish = None
        for raw_line in resp:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for ch in chunk.get("choices") or []:
                delta = ch.get("delta") or {}
                piece = delta.get("content") or ""
                if piece:
                    parts.append(piece)
                    chars += len(piece)
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
            if max_output_chars is not None and chars > max_output_chars:
                raise _StreamLimitExceeded("".join(parts))
        text = "".join(parts)
        if finish == "length":
            print(
                "    [warn] completion hit max_tokens=%d — output truncated"
                % max_tokens,
                file=sys.stderr,
            )
        return text


def _json_block(text):
    """Extract the first balanced JSON object from model output."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _json_complete(messages, schema=None, max_tokens=2048, attempts=2, verbose=False,
                   temperature=0.0):
    """Constrained JSON completion: schema-enforced.

    The first attempt uses `temperature`; when the JSON does not parse, the
    retry raises it to LLM_RETRY_TEMPERATURE so the model explores a
    different sample instead of re-emitting the identical broken JSON.
    """
    for attempt in range(attempts):
        attempt_temp = (
            temperature
            if (attempt == 0 or temperature != 0.0)
            else LLM_RETRY_TEMPERATURE
        )
        raw = _chat_completion(
            messages, max_tokens=max_tokens, schema=schema,
            temperature=attempt_temp,
        )
        block = _json_block(raw)
        if block is None:
            if verbose:
                print("      JSON parse failed (attempt %d): %r" % (attempt + 1, raw[:120]))
            continue
        try:
            return json.loads(block)
        except json.JSONDecodeError:
            if verbose:
                print("      JSON decode failed (attempt %d)" % (attempt + 1))
            continue
    return None
