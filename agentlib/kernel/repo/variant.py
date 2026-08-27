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


def _existing_variant_alias(attr, meth, repo_interface):
    """Return an EXISTING repo method name that `meth` is a name-variant of,
    or None. Used to synthesize a delegating alias instead of a stub."""
    sig = repo_interface.get(attr) or {}
    for m in sig:
        if m != meth and _method_name_variant(m, meth):
            return m
    return None


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
