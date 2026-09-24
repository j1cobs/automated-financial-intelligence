"""Phase 28c: the category set is closed, and normalising it never destroys
a hand-made correction it merely failed to understand.

`update_transaction_category` accepted arbitrary free text, so the effective
category set was the 18 canonical names *plus every string ever typed*. Budget
caps are keyed on category, so an open set means orphan budget rows and a list
that grows without bound.
"""

import unittest

from analytics.categories import (
    CANONICAL_CATEGORIES,
    LEGACY_CATEGORY_MAP,
    canonicalize,
    is_canonical,
)


class CanonicalSetTests(unittest.TestCase):
    def test_matches_the_taxonomy_migration(self):
        self.assertEqual(len(CANONICAL_CATEGORIES), 18)
        self.assertIn("FOOD_AND_DRINK", CANONICAL_CATEGORIES)
        self.assertIn("UNCATEGORIZED", CANONICAL_CATEGORIES)
        self.assertIn("OTHER", CANONICAL_CATEGORIES)

    def test_every_name_is_upper_snake_case(self):
        for name in CANONICAL_CATEGORIES:
            self.assertEqual(name, name.upper())
            self.assertNotIn(" ", name)

    def test_is_canonical(self):
        self.assertTrue(is_canonical("TRANSPORTATION"))
        self.assertFalse(is_canonical("Transport"))
        self.assertFalse(is_canonical("reno"))


class CanonicalizeTests(unittest.TestCase):
    def test_canonical_input_passes_through(self):
        self.assertEqual(canonicalize("FOOD_AND_DRINK"), "FOOD_AND_DRINK")

    def test_case_and_whitespace_are_normalised(self):
        self.assertEqual(canonicalize("  food_and_drink  "), "FOOD_AND_DRINK")

    def test_spaces_map_to_underscores(self):
        self.assertEqual(canonicalize("Food and Drink"), "FOOD_AND_DRINK")

    def test_known_legacy_names_map(self):
        self.assertEqual(canonicalize("Dining"), "FOOD_AND_DRINK")
        self.assertEqual(canonicalize("Groceries"), "FOOD_AND_DRINK")
        self.assertEqual(canonicalize("Transport"), "TRANSPORTATION")
        self.assertEqual(canonicalize("Utilities"), "RENT_AND_UTILITIES")
        self.assertEqual(canonicalize("Housing"), "RENT_AND_UTILITIES")
        self.assertEqual(canonicalize("Health"), "MEDICAL")
        self.assertEqual(canonicalize("Shopping"), "GENERAL_MERCHANDISE")
        self.assertEqual(canonicalize("Subscriptions"), "GENERAL_SERVICES")
        self.assertEqual(canonicalize("ATM"), "TRANSFER_OUT")

    def test_legacy_map_only_targets_canonical_names(self):
        for target in LEGACY_CATEGORY_MAP.values():
            self.assertIn(target, CANONICAL_CATEGORIES)

    def test_every_legacy_name_from_migration_024_is_covered(self):
        """Migration 024 listed the Phase-1 names. Each should map, so an
        existing correction against one of them is not left stranded."""
        legacy = [
            "ATM", "Dining", "Entertainment", "Groceries", "Health", "Housing",
            "Income", "Savings", "Shopping", "Subscriptions", "Transfer",
            "Transport", "Travel", "Utilities",
        ]
        for name in legacy:
            with self.subTest(name=name):
                self.assertIsNotNone(canonicalize(name), f"{name} has no mapping")

    # The point of the whole exercise: an unrecognised value is reported, not
    # guessed at and not silently flattened to OTHER.
    def test_unrecognised_free_text_returns_none(self):
        self.assertIsNone(canonicalize("Alexie phone"))
        self.assertIsNone(canonicalize("reno"))
        self.assertIsNone(canonicalize("misc stuff 2024"))

    def test_never_falls_back_to_other(self):
        self.assertNotEqual(canonicalize("something nobody mapped"), "OTHER")

    def test_empty_and_none_return_none(self):
        self.assertIsNone(canonicalize(""))
        self.assertIsNone(canonicalize("   "))
        self.assertIsNone(canonicalize(None))

    def test_a_near_miss_is_not_guessed(self):
        """No fuzzy matching: 'FOOD' is not close enough to FOOD_AND_DRINK to
        rewrite someone's data on."""
        self.assertIsNone(canonicalize("FOOD"))


if __name__ == "__main__":
    unittest.main()
