"""Service kernel recipes.

Each recipe module here declares `RECIPES = [Recipe(name, priority, fn)]`.
`dispatch_impl_body` loads them via `load_recipes_for` and picks the one whose
name matches `impl["kind"]`, preserving the original `_IMPL_HANDLERS` mapping.
"""
import inspect

from ..load import load_recipes_for
from . import (  # noqa: F401  (import to register packages; pkgutil reads __path__)
    below_foreign_threshold,
    contract_effects,
    count_by_group,
    create_child_row,
    duplicate_groups,
    export_csv,
    report_parts,
    sum_by_group,
    total_filtered,
    total_in_period,
)
from .common import _impl_bindings_ok


def _takes_exception_names(fn):
    """True when a recipe declares the optional ``exception_names`` parameter.

    Recipes that load a row by a caller-supplied id need the project's
    DESIGNED exception class names to report a miss as a not-found instead of
    a silent ``False``; recipes that never look a row up do not. Passing the
    argument only where it is declared keeps every other recipe's signature
    untouched.
    """
    try:
        return "exception_names" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def dispatch_impl_body(m, impl, ent, entities_by_class, exception_names=None):
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
            if _takes_exception_names(recipe.fn):
                return recipe.fn(m, impl, ent_design, entities_by_class,
                                 exception_names=exception_names)
            return recipe.fn(m, impl, ent_design, entities_by_class)
    return None


def declared_money_keys(impl):
    """Money RESULT keys a recipe declares for an impl, computed from the impl
    ALONE — or ``{}`` when the kind declares none.

    A recipe may stamp a display table on the method while rendering, but the
    CLI file is rendered BEFORE the service bodies, so the CLI renderer cannot
    read it. Exposing the table as a pure function of the impl lets the
    pipeline compute it up front and stamp the method before the CLI runs.
    """
    kind = impl.get("kind") if isinstance(impl, dict) else None
    if not kind:
        return {}
    for recipe in load_recipes_for(__package__):
        if recipe.name == kind and recipe.money_keys is not None:
            return recipe.money_keys(impl) or {}
    return {}
