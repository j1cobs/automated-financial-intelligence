from __future__ import annotations

import unittest

import pandas as pd

from analytics.placeholders import build_placeholder_models


class PlaceholderModelTests(unittest.TestCase):
    def test_placeholder_models_preserve_rows_and_mark_defaults(self) -> None:
        models = build_placeholder_models()
        frame = pd.DataFrame(
            {
                "description": ["Coffee Shop", "Monthly Subscription"],
                "amount": [5.25, 14.99],
            }
        )

        categorized = frame.copy()
        categorized["category"] = models.classifier.categorize(categorized["description"])
        scored = models.outlier_detector.score(categorized)

        self.assertEqual(list(scored["category"]), ["Uncategorized", "Uncategorized"])
        self.assertTrue((scored["outlier_score"] == 0.0).all())
        self.assertTrue((~scored["is_outlier"]).all())


if __name__ == "__main__":
    unittest.main()
