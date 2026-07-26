from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from analytics.classifier import TransactionClassifier


class TransactionClassifierTests(unittest.TestCase):
    def test_falls_back_to_rules_without_model(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            model_path = Path(tmp_dir) / "missing.joblib"
            classifier = TransactionClassifier(str(model_path))
            categories = classifier.categorize(pd.Series(["NETFLIX MONTHLY", "Unknown Payment"]))

        self.assertEqual(categories.iloc[0], "subscriptions")
        self.assertEqual(categories.iloc[1], "uncategorized")


if __name__ == "__main__":
    unittest.main()
