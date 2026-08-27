"""Recipe discovery via pkgutil over the kernel subpackages.

Each recipe module under a kernel subpackage (e.g. `kernel/repo/`,
`kernel/service/`) declares a module-level `RECIPES = [Recipe(...)]` list.
Importing `load_recipes_for` walks that subpackage's modules, aggregates
their RECIPES lists, and sorts by priority. Adding a new recipe file needs
no edit to any central list.
"""
import importlib
import pkgutil
from typing import List

from .recipe_types import Recipe


def _recipes_in_module(mod):
    return list(getattr(mod, "RECIPES", []) or [])


def load_recipes_for(package) -> List[Recipe]:
    """Return all Recipe objects declared by modules under `package`.

    `package` may be a module or subpackage that has a `__path__` (i.e. an
    importable subpackage), or the dotted import path of such a subpackage
    (a string, e.g. `__package__`). Modules are imported so their `RECIPES`
    binding executes. Ordering is by `priority`.
    """
    if isinstance(package, str):
        package = importlib.import_module(package)
    if not hasattr(package, "__path__"):
        return []
    out = []
    for modinfo in pkgutil.iter_modules(package.__path__):
        mod = importlib.import_module(package.__name__ + "." + modinfo.name)
        out.extend(_recipes_in_module(mod))
    return sorted(out, key=lambda r: r.priority)
