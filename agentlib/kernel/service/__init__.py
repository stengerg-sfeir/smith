"""Service kernel recipes.

Each recipe module here declares `RECIPES = [Recipe(name, priority, fn)]`.
`dispatch_impl_body` loads them via `load_recipes_for` and picks the one whose
name matches `impl["kind"]`, preserving the original `_IMPL_HANDLERS` mapping.
"""
from ..load import load_recipes_for
from . import (  # noqa: F401  (import to register packages; pkgutil reads __path__)
    below_foreign_threshold,
    duplicate_groups,
    export_csv,
    sum_by_group,
    total_filtered,
    total_in_period,
)
from .common import _impl_bindings_ok


def dispatch_impl_body(m, impl, ent, entities_by_class):
    """Return the deterministic body for a designed service `impl`, or None.

    Mirrors the original `_IMPL_HANDLERS` dict dispatch: bindings are
    cross-checked first, then the recipe whose name equals `impl["kind"]`
    is invoked.
    """
    kind = impl.get("kind")
    cls_name, ent_design = _impl_bindings_ok(impl, m, entities_by_class)
    if not ent_design:
        return None
    for recipe in load_recipes_for(__package__):
        if recipe.name == kind:
            return recipe.fn(m, impl, ent_design, entities_by_class)
    return None
