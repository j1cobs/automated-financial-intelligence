from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from analytics.outlier_detector import OutlierDetector


class OutlierDetectorTests(unittest.TestCase):
    def test_score_empty_frame(self) -> None:
        frame = pd.DataFrame(columns=["category", "amount"])
        scored = OutlierDetector().score(frame)
        self.assertIn("outlier_score", scored.columns)
        self.assertIn("is_outlier", scored.columns)
        self.assertTrue(scored.empty)

    def test_score_small_group_uses_zscore(self) -> None:
        # Small groups (< min_group_size=8) use the z-score branch. Note: with a
        # population std (ddof=0) over N points, Samuelson's inequality bounds any
        # single point's z-score at sqrt(N-1) — for N<8 that max is sqrt(6)~=2.449,
        # always below the is_outlier>3 threshold. So a small group can never trip
        # is_outlier=True; this test instead verifies the z-score math itself: the
        # extreme row gets by far the highest outlier_score in the group.
        amounts = [10.0, 10.0, 10.0, 10.0, 100.0]
        frame = pd.DataFrame(
            {
                "category": ["Groceries"] * len(amounts),
                "amount": amounts,
            }
        )
        scored = OutlierDetector().score(frame)

        values = np.array(amounts)
        mean = values.mean()
        std = values.std()
        expected_scores = np.abs((values - mean) / std)

        np.testing.assert_allclose(scored["outlier_score"].to_numpy(), expected_scores)
        self.assertEqual(scored["outlier_score"].idxmax(), 4)
        self.assertFalse(scored["is_outlier"].any())

    def test_score_large_group_uses_isolation_forest(self) -> None:
        uniform_amounts = [
            10.0,
            12.0,
            11.0,
            9.0,
            13.0,
            10.0,
            11.0,
            12.0,
            9.0,
            10.0,
            11.0,
            13.0,
            10.0,
            12.0,
            11.0,
            9.0,
            10.0,
            12.0,
            11.0,
            10.0,
        ]
        amounts = uniform_amounts + [5000.0]
        frame = pd.DataFrame(
            {
                "category": ["Groceries"] * len(amounts),
                "amount": amounts,
            }
        )
        scored = OutlierDetector().score(frame)

        outlier_row = scored.iloc[-1]
        self.assertTrue(bool(outlier_row["is_outlier"]))

    def test_score_preserves_all_rows(self) -> None:
        frame = pd.DataFrame(
            {
                "category": ["Groceries", "Dining", "Groceries"],
                "amount": [10.0, 20.0, 15.0],
            }
        )
        scored = OutlierDetector().score(frame)
        self.assertEqual(len(scored), len(frame))

    def test_outlier_score_dtype(self) -> None:
        frame = pd.DataFrame(
            {
                "category": ["Groceries", "Dining", "Groceries"],
                "amount": [10.0, 20.0, 15.0],
            }
        )
        scored = OutlierDetector().score(frame)
        self.assertEqual(scored["outlier_score"].dtype, np.float64)


if __name__ == "__main__":
    unittest.main()
