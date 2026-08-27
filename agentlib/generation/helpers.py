"""Type-hint and method-signature helpers for the deterministic renderers.

Extracted from agent.py. `_sanitize_type_hint` normalizes LLM pseudo-types;
`_method_stub_code` renders a locked NotImplementedError method signature.
No behaviour change.
"""


def _sanitize_type_hint(t):
    """Normalize LLM pseudo-type hints into valid Python type expressions.

    - `int?` / `datetime.date?` -> `Optional[int]` / `Optional[datetime.date]`
    - `int | None` -> `Optional[int]`
    - `Task?` / `Task | None` -> `Optional[Task]`
    - `Dict[str, any]` -> `Dict[str, Any]`
    - `List[Item]`, `str`, `bool`, `Any` pass through
    """
    t = (t or "").strip()
    if not t:
        return "Any"
    if t.endswith("?"):
        return "Optional[" + _sanitize_type_hint(t[:-1]) + "]"
    if t == "any":
        return "Any"
    if t == "None":
        return "None"
    if "|" in t:
        parts = [p.strip() for p in t.split("|")]
        parts = [_sanitize_type_hint(p) for p in parts]
        if "None" in parts:
            inner = [p for p in parts if p != "None"]
            return "Optional[%s]" % (inner[0] if len(inner) == 1 else "Union[%s]" % ", ".join(inner))
        return "Union[%s]" % ", ".join(parts)
    # Recurse into generics
    for base in ("List[", "Dict[", "Optional[", "Union["):
        if t.startswith(base) and t.endswith("]"):
            inner = t[len(base) : -1]
            # split on top-level commas only
            parts = []
            depth = 0
            cur = []
            for ch in inner:
                if ch in "[(":
                    depth += 1
                elif ch in "])":
                    depth -= 1
                if ch == "," and depth == 0:
                    parts.append("".join(cur).strip())
                    cur = []
                else:
                    cur.append(ch)
            if cur:
                parts.append("".join(cur).strip())
            mapped = [_sanitize_type_hint(p) for p in parts]
            return base[:-1] + "[%s]" % ", ".join(mapped)
    return t


def _method_stub_code(m, indent=4):
    """def line for a design method; body = NotImplementedError.

    Parameter order is preserved, but once an Optional param is seen every
    following param is defaulted (`= None`) so the signature never violates
    Python's "non-default follows default" rule.
    """
    name = m.get("name")
    params = m.get("params") or []
    sig_parts = []
    seen_optional = False
    for p in params:
        ptype = _sanitize_type_hint(p.get("type") or "")
        if ptype.startswith("Optional["):
            seen_optional = True
            sig_parts.append("%s: %s = None" % (p["name"], ptype))
        elif seen_optional:
            sig_parts.append("%s: %s = None" % (p["name"], ptype))
        elif ptype.startswith("List[") or ptype.startswith("Dict["):
            sig_parts.append("%s: %s" % (p["name"], ptype))
        else:
            sig_parts.append("%s: %s" % (p["name"], ptype))
    sig = ", ".join(sig_parts)
    if sig:
        sig = "self, " + sig
    else:
        sig = "self"
    ret = _sanitize_type_hint(m.get("returns") or "None")
    return '    ' * indent + "def %s(%s) -> %s:\n%s    raise NotImplementedError()" % (
        name, sig, ret, "    " * indent,
    )
