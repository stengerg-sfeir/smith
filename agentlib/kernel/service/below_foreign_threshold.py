"""Service recipe: rows whose value_field is below a related entity's threshold.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _camel, _snake
from ..recipe_types import Recipe


def _h_below_foreign_threshold(m, impl, ent, entities_by_class):
    """Rows whose value_field is strictly below the related entity's
    threshold field (joined through the FK), e.g.
    product.stock_qty < product.category.reorder_threshold."""
    var = _snake(impl["entity"])
    ref_var = _snake(_camel(impl["ref_entity"]))
    vf, ff, fk = impl["value_field"], impl["ref_field"], impl["fk_field"]
    return [
        "        results = []",
        "        thresholds = {}",
        "        for ref_row in self.%s_repo.get_all():" % ref_var,
        "            if ref_row.%s is not None:" % ff,
        "                thresholds[ref_row.id] = ref_row.%s" % ff,
        "        for row in self.%s_repo.list():" % var,
        "            threshold = thresholds.get(row.%s)" % fk,
        "            if threshold is not None and row.%s < threshold:" % vf,
        "                results.append(row)",
        "        return results",
    ]


RECIPES = [Recipe("below_foreign_threshold", 15, _h_below_foreign_threshold)]
