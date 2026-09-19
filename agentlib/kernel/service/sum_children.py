"""Service recipe: sum a child entity's quantity * price for a parent id.

Registered as a discoverable `RECIPES` list under the kernel service package.
"""
from ...naming import _snake
from ..recipe_types import Recipe


def _h_sum_children(m, impl, ent, entities_by_class):
    """Sum ``value_field * price_field`` over the child rows belonging to a
    parent id (e.g. InvoiceLine rows filtered by ``invoice_id``).

    Fully design-driven: ``impl`` carries the child entity, the FK column to
    filter on, the two per-line numeric fields to multiply, and the service
    method's own parent-id parameter name. No domain vocabulary here."""
    child = _snake(impl["entity"])
    fk = impl["fk_field"]
    vf = impl["value_field"]
    pid = impl["parent_id_param"]
    price_via = impl.get("price_via")
    if isinstance(price_via, dict):
        # The line carries a QUANTITY but no price of its own: the price lives
        # on the entity the line references ("Each line references a product
        # and quantity. The invoice total must be calculated from its lines",
        # prompt 28). Each referenced row is looked up through ITS OWN
        # repository — a missing row contributes nothing rather than aborting
        # the total.
        return [
            "        rows = self.%s_repo.list(%s=%s)" % (child, fk, pid),
            "        total = 0.0",
            "        for row in rows:",
            "            _ref = self.%s_repo.get_by_id(row.%s)"
            % (_snake(price_via["ref_entity"]), price_via["fk_field"]),
            "            _price = _ref.%s if _ref is not None else 0.0"
            % price_via["price_field"],
            "            total += row.%s * float(_price)" % vf,
            "        return total",
        ]
    pf = impl["price_field"]
    return [
        "        rows = self.%s_repo.list(%s=%s)" % (child, fk, pid),
        "        return sum(row.%s * float(row.%s) for row in rows)" % (vf, pf),
    ]


RECIPES = [Recipe("sum_children", 16, _h_sum_children)]
