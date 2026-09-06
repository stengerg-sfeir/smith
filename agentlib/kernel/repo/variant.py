"""Repository variant-alias recipe: delegate a name-variant method to an
existing one.

Registered as a discoverable `RECIPES` list under the kernel repo package.
"""
from ..recipe_types import Recipe


def _method_name_variant(a, b):
    """True when two repo-method names differ only by a verb prefix
    (get_/find_/list_/fetch_/count_/top_/all_) or an entity-suffix, e.g.
    `top_products_by_total_quantity_sold` vs `get_top_products_by_total_quantity_sold`
    or `get_all_orders` vs `get_all`."""
    def norm(s):
        # Strip only CRUD verb prefixes — NOT semantic prefixes like top_/
        # latest_/all_ which are part of the method's meaning (so
        # get_top_products_... and top_products_... normalize identically).
        for pre in ("get_", "find_", "list_", "fetch_", "count_"):
            if s.startswith(pre):
                s = s[len(pre):]
                break
        return s
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    return na.startswith(nb + "_") or nb.startswith(na + "_")


def _existing_variant_alias(attr, meth, repo_interface, call_args=None):
    """Return an EXISTING repo method name that `meth` is a name-variant of,
    or None. Used to synthesize a delegating alias instead of a stub.

    When several candidates are name-variants, prefer the one whose parameter
    set covers the call's positional/keyword argument names (``call_args``),
    so ``find_by_member_id_and_book_id(member_id, book_id)`` aliases to
    ``get_loans_by_member_and_book`` (params member_id, book_id) rather than
    ``find_by_member_id`` (params member_id) — the latter would alias a 2-arg
    call onto a 1-arg method and fail validation on arity.
    """
    sig = repo_interface.get(attr) or {}
    if not sig:
        return None
    call_args = call_args or []

    def _param_vals(m):
        return [p[0] if isinstance(p, tuple) else p for p in (sig.get(m) or [])]

    def _score(m):
        if m == meth:
            return (-1000, 0, 0)
        pv = _param_vals(m)
        # How many call args the candidate's param set covers.
        matched = sum(1 for p in call_args if p in pv)
        variant = 1 if _method_name_variant(m, meth) else 0
        return (matched, variant, -len(pv))

    best = max(sig, key=_score)
    # Only alias on real signal: a strict name-variant, or at least one call
    # arg the candidate's param set covers. Prevents random aliasing.
    if _score(best)[0] == 0 and not _method_name_variant(best, meth):
        return None
    return best


def _render_variant_alias(meth, existing):
    """Delegating alias body: `def <meth>(...): return self.<existing>(...)`."""
    return (
        "    def %s(self, *args, **kwargs):\n"
        "        return self.%s(*args, **kwargs)\n" % (meth, existing)
    )


def _try_variant_body(attr, meth, repo_interface):
    """Recipe fn: return a delegating alias body when a variant exists."""
    existing = _existing_variant_alias(attr, meth, repo_interface)
    if existing is None:
        return None
    return [_render_variant_alias(meth, existing)]


RECIPES = [Recipe("variant_alias", 30, _try_variant_body)]
