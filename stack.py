import unittest
from collections import Counter
from operator import attrgetter
from dataclasses import replace

from vendus import InvoiceItem, InvoiceModifier


def stack_items(items, sold_seperatly_references):
    stacked_items = []

    for item in items:
        for modifier in item.modifiers:
            if modifier.reference in sold_seperatly_references:
                sold_seperatly_item = InvoiceItem(
                    reference=modifier.reference,
                    price=modifier.price,
                    quantity=modifier.quantity,
                    note=modifier.note,
                    modifiers=tuple(),
                )

                stacked_items.append(sold_seperatly_item)

        item_without_sold_separately_modifiers = replace(
            item,
            modifiers=tuple(
                modifer
                for modifier in item.modifiers
                if modifier.reference not in sold_seperatly_references
            ),
        )

        stacked_items.append(item_without_sold_separately_modifiers)

    expanded_items = []

    for item in stacked_items:
        for _ in range(item.quantity):
            expanded_items.append(
                replace(
                    item,
                    quantity=1,
                )
            )

    items_counter = Counter(expanded_items)

    stacked_items = [
        replace(item, quantity=count) for item, count in items_counter.items()
    ]

    return sorted(stacked_items, key=attrgetter("reference"))


class TestStack(unittest.TestCase):
    def test_stack(self):
        items = [
            InvoiceItem(
                reference="PEPSI",
                quantity=1,
                price=None,
                modifiers=tuple(),
                note="some note",
            ),
            InvoiceItem(
                reference="PEPSI", quantity=1, price=None, modifiers=tuple(), note=None
            ),
            InvoiceItem(
                reference="PEPSI", quantity=1, price=None, modifiers=tuple(), note=None
            ),
            InvoiceItem(
                reference="COKE", quantity=1, price=None, modifiers=tuple(), note=None
            ),
            InvoiceItem(
                reference="COKE", quantity=2, price=None, modifiers=tuple(), note=None
            ),
            InvoiceItem(
                reference="PEPSI", quantity=1, price=2.0, modifiers=tuple(), note=None
            ),
            InvoiceItem(
                reference="FOOD",
                quantity=1,
                price=None,
                note=None,
                modifiers=[
                    InvoiceModifier(reference="COKE", quantity=2, price=None, note=None)
                ],
            ),
        ]

        stacked_items = stack_items(items, {"COKE", "PEPSI"})

        self.assertIn(
            InvoiceItem(
                reference="COKE", quantity=5, price=None, modifiers=tuple(), note=None
            ),
            stacked_items,
        )
        self.assertIn(
            InvoiceItem(
                reference="PEPSI", quantity=2, price=None, modifiers=tuple(), note=None
            ),
            stacked_items,
        )
        self.assertIn(
            InvoiceItem(
                reference="PEPSI", quantity=1, price=2.0, modifiers=tuple(), note=None
            ),
            stacked_items,
        )
        self.assertIn(
            InvoiceItem(
                reference="PEPSI",
                quantity=1,
                price=None,
                modifiers=tuple(),
                note="some note",
            ),
            stacked_items,
        )
        self.assertIn(
            InvoiceItem(
                reference="FOOD", quantity=1, price=None, modifiers=tuple(), note=None
            ),
            stacked_items,
        )


if __name__ == "__main__":
    unittest.main()
