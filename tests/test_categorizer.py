from __future__ import annotations

import unittest

import pandas as pd

from analytics.categorizer import CascadeCategorizer, merchant_key


class MerchantKeyTests(unittest.TestCase):
    def test_cafe_du_parquet_three_spellings_collide(self) -> None:
        """The exact 3-way collision from the plan's Step-0 probe: one real merchant,
        three raw spellings, must normalize to the identical key."""
        key_a = merchant_key("Cafe Du Parquet", "Cafe Du Parquet")
        key_b = merchant_key(None, "CAFE DU PARQUET MONTREAL QC")
        key_c = merchant_key(None, "Purchase /CAFE DU PARQUET")
        self.assertEqual(key_a, key_b)
        self.assertEqual(key_b, key_c)

    def test_metro_store_numbers_collapse_identically(self) -> None:
        key_a = merchant_key(None, "METRO #4521 MONTREAL QC")
        key_b = merchant_key(None, "METRO #7832 QUEBEC QC")
        self.assertEqual(key_a, key_b)

    def test_different_merchants_do_not_over_merge(self) -> None:
        self.assertNotEqual(merchant_key(None, "SAQ"), merchant_key(None, "IKEA"))

    def test_non_canadian_trailing_code_is_not_stripped(self) -> None:
        """Regression: an unrestricted trailing-2-letter-code strip previously ate
        "EATS US" off "Uber Eats US" as if "US" were a province code."""
        self.assertEqual(merchant_key(None, "Uber Eats US"), "UBER EATS US")

    def test_empty_description_does_not_crash(self) -> None:
        self.assertEqual(merchant_key(None, ""), "")

    def test_none_description_does_not_crash(self) -> None:
        self.assertEqual(merchant_key(None, None), "")


class CascadeCategorizerTests(unittest.TestCase):
    def test_merchant_memory_beats_plaid_pfc(self) -> None:
        frame = pd.DataFrame(
            {
                "merchant_name": ["Couche-Tard"],
                "description": ["Couche-Tard"],
                "pfc_primary": ["TRANSPORTATION"],
            }
        )
        lookup = {merchant_key("Couche-Tard", "Couche-Tard"): "FOOD_AND_DRINK"}

        result = CascadeCategorizer().categorize(frame, lookup)

        self.assertEqual(result["category"].iloc[0], "FOOD_AND_DRINK")
        self.assertEqual(result["category_source"].iloc[0], "merchant")

    def test_plaid_pfc_used_when_no_merchant_memory_hit(self) -> None:
        frame = pd.DataFrame(
            {
                "merchant_name": ["Some New Merchant"],
                "description": ["Some New Merchant"],
                "pfc_primary": ["GENERAL_MERCHANDISE"],
            }
        )

        result = CascadeCategorizer().categorize(frame, {})

        self.assertEqual(result["category"].iloc[0], "GENERAL_MERCHANDISE")
        self.assertEqual(result["category_source"].iloc[0], "plaid")

    def test_fallback_to_uncategorized_when_neither_available(self) -> None:
        frame = pd.DataFrame(
            {
                "merchant_name": [None],
                "description": ["Unknown Row"],
                "pfc_primary": [None],
            }
        )

        result = CascadeCategorizer().categorize(frame, {})

        self.assertEqual(result["category"].iloc[0], "UNCATEGORIZED")
        self.assertEqual(result["category_source"].iloc[0], "none")

    def test_empty_merchant_lookup_falls_through_to_plaid(self) -> None:
        frame = pd.DataFrame(
            {
                "merchant_name": ["Metro"],
                "description": ["Metro"],
                "pfc_primary": ["FOOD_AND_DRINK"],
            }
        )

        result = CascadeCategorizer().categorize(frame, {})

        self.assertEqual(result["category"].iloc[0], "FOOD_AND_DRINK")
        self.assertEqual(result["category_source"].iloc[0], "plaid")

    def test_missing_columns_do_not_raise_key_error(self) -> None:
        """Documented behavior: a frame lacking merchant_name/pfc_primary/description
        entirely (e.g. a future non-Plaid source) must not raise KeyError."""
        frame = pd.DataFrame({"amount": [10.0, 20.0]})

        result = CascadeCategorizer().categorize(frame, {})

        self.assertEqual(list(result["category"]), ["UNCATEGORIZED", "UNCATEGORIZED"])
        self.assertEqual(list(result["category_source"]), ["none", "none"])

    def test_empty_frame_returns_empty_frame_with_expected_columns(self) -> None:
        frame = pd.DataFrame(columns=["merchant_name", "description", "pfc_primary"])

        result = CascadeCategorizer().categorize(frame, {})

        self.assertTrue(result.empty)
        self.assertIn("category", result.columns)
        self.assertIn("category_source", result.columns)


if __name__ == "__main__":
    unittest.main()
