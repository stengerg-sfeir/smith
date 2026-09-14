"""Field defaults transcribed from the SPECIFICATION alone.

The design LLM is explicitly asked to stamp ``"default"`` next to a field when
the spec declares one (the field-schema instruction in ``agentlib/design.py``
spells out ``"is_active (default True)" -> "default": true``), but a 4B model
drops it. ``library_system`` then renders ``Member.is_active`` as a REQUIRED
constructor argument, so the spec's default is silently lost (S16).

This module transcribes the defaults from the PROMPT TEXT — never from
generated code, and never from the design — and the caller stamps them into
the design's entity fields before the model renderer runs. It is deliberately
literal: only a default written in the spec next to a field name is honoured,
and only for a field that already exists in a designed entity, so a stray
sentence ("... optional (default None) in the domain models") cannot invent a
field or mutate a model the spec never described.
"""

import re

from ..generation.model_render import _coerce_field_default

# ``available_copies (default 1)`` / ``low_active (optional bool, default
# False, whether ...)`` / ``is_active (default True)``: a field name followed
# by a parenthesised list that contains the word "default".
_PARENTHESISED = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)\n]*)\)")

# ``is_active defaults to True`` / ``stock_qty default 0``.
_INLINE = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s+defaults?\s+(?:to\s+)?([^,.;\n]+)"
)

# The value after the word "default" inside a parenthesised list.
_INNER_DEFAULT = re.compile(r"\bdefaults?\s+(?:to\s+)?([^,\n]+)", re.IGNORECASE)

# ``payment_method (cash/card/transfer)`` / ``status (active/returned/overdue)``:
# a field name INSIDE a comma-separated model description, followed by a
# parenthesised SLASH list of the values the field may take. The leading
# ``(?:^|[,\n])`` is load-bearing: the prompt also writes prose such as
# "budget status (on_track/warning/exceeded)", where ``status`` is preceded by
# a bare space rather than a field separator. Requiring a comma (or a line
# start) keeps the scan on the field-list prose and off the sentences.
_ENUM_FIELD = re.compile(
    r"(?:^|[,\n])\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)\n]*)\)"
)

# A parenthesised list of bare slash-separated identifiers, e.g.
# ``cash/card/transfer``. A phrase ("str, ISO date") is not one.
_SLASH_LIST = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*(?:\s*/\s*[A-Za-z_][A-Za-z0-9_]*)+"
)

_INT_LITERAL = re.compile(r"[+-]?\d+")
_FLOAT_LITERAL = re.compile(r"[+-]?\d+\.\d+")
_QUOTED_LITERAL = re.compile(r"['\"]([^'\"]*)['\"]")
# A bare identifier may name a str default (``payment_method (default cash)``).
_WORD_LITERAL = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

_TRUE = ("true", "yes")
_FALSE = ("false", "no")
_NULL = ("none", "null", "nothing")


def _coerce_literal(literal):
    """The Python value a spec literal denotes, or ``None`` when not a default.

    ``None`` is returned for an explicit null spelling, which means "no
    default" rather than a default of ``None``: a dataclass field with an
    ``Optional`` annotation already defaults to ``None``, and the renderer
    treats a missing default as "required", which is the status quo.
    """
    text = literal.strip().rstrip(").,;:")
    if not text:
        return None
    low = text.lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    if low in _NULL:
        return None
    if _INT_LITERAL.fullmatch(text):
        return int(text)
    if _FLOAT_LITERAL.fullmatch(text):
        return float(text)
    quoted = _QUOTED_LITERAL.fullmatch(text)
    if quoted:
        return quoted.group(1)
    if _WORD_LITERAL.fullmatch(text):
        return text
    # A phrase such as ``default value`` is prose, not a default. The
    # renderer's type coercion would reject it anyway; drop it here so the
    # extraction never records noise.
    return None


def extract_model_defaults(prompt_text):
    """``{<field>: <literal>}`` transcribed from the specification text.

    The CLASS name is deliberately not part of this scan: the spec states a
    model as a bare field list ("id, name, email (unique), is_active (default
    True)"), so only the field name can be recovered here. The caller matches
    each field against the designed entities, which means a default declared
    for a field no model carries is simply never applied — and a default can
    never be attached to the wrong class.
    """
    found = {}
    if not prompt_text:
        return found

    def _record(name, literal):
        value = _coerce_literal(literal)
        if value is None:
            return
        found[name] = value

    for match in _PARENTHESISED.finditer(prompt_text):
        # ``(optional bool, default False, whether ...)`` — the value stops at
        # the first comma, so the trailing prose never leaks into the literal.
        inner = _INNER_DEFAULT.search(match.group(2))
        if inner is None:
            continue
        _record(match.group(1), inner.group(1))

    for match in _INLINE.finditer(prompt_text):
        _record(match.group(1), match.group(2))

    # ``payment_method (cash/card/transfer)`` — the spec states the field's
    # allowed VALUES and brackets its CLI flag as optional, so the field must
    # carry the first value as a default. Otherwise the renderer makes it a
    # REQUIRED constructor argument and the CLI refuses
    # ``expense add --amount ... --description ... --category ...`` for a
    # missing ``--method`` the specification writes as ``[--method]``.
    # LOWER priority than a literal "default": an explicit default wins.
    for match in _ENUM_FIELD.finditer(prompt_text):
        inner = match.group(2).strip()
        if not _SLASH_LIST.fullmatch(inner):
            continue
        found.setdefault(match.group(1), inner.split("/")[0].strip())

    return found


def apply_model_defaults(designs, defaults, verbose=False):
    """Stamp spec-declared defaults onto fields whose design cannot supply one.

    Only a field that already exists in a designed entity can be stamped, so a
    default declared for a field no model carries is never applied and can
    never land on the wrong class. A field whose design carries a RENDERABLE
    default is left untouched — the design's value wins; this pass only fills
    the gap the model left, which includes the case where it stamped a default
    the renderer must reject (see the coercion note below).
    Returns the list of ``(class, field, value)`` stamped.
    """
    applied = []
    for _path, kind, data in designs or []:
        if kind != "models" or not isinstance(data, dict):
            continue
        for ent in data.get("entities") or []:
            if not isinstance(ent, dict):
                continue
            for field in ent.get("fields") or []:
                if not isinstance(field, dict):
                    continue
                fname = field.get("name")
                if fname not in defaults:
                    continue
                # The design's own default wins ONLY when the renderer will
                # actually emit it. The renderer coerces a designed default
                # STRICTLY (``_coerce_field_default``), so a malformed value —
                # the 4B model is known to emit ``{"value": "cash"}`` for a str
                # field — is REJECTED and the field silently renders as
                # REQUIRED, losing the spec's default entirely (library_system:
                # ``available_copies (default 1)`` / ``is_active (default
                # True)``). Such a value does not count as "already defaulted".
                if _coerce_field_default(
                    field.get("type", "str"), field.get("default")
                ) is not None:
                    continue
                field["default"] = defaults[fname]
                applied.append((ent.get("name"), fname, defaults[fname]))
    if verbose:
        for cls, fname, value in applied:
            print("    [models] %s.%s: default %r from the spec" % (cls, fname, value))
    return applied
