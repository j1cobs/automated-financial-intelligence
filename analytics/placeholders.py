from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class PlaceholderModelBundle:
    classifier: "PlaceholderTransactionClassifier"
    outlier_detector: "PlaceholderOutlierDetector"


class PlaceholderTransactionClassifier:
    def __init__(self, default_category: str = "Uncategorized") -> None:
        self.default_category = default_category

    def load(self) -> None:
        return None

    def train(self, *args, **kwargs) -> None:
        return None

    def categorize(self, descriptions: pd.Series) -> pd.Series:
        return pd.Series(
            [self.default_category] * len(descriptions),
            index=descriptions.index,
            dtype="object",
        )


class PlaceholderOutlierDetector:
    def score(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            scored = frame.copy()
            scored["outlier_score"] = pd.Series(dtype=float)
            scored["is_outlier"] = pd.Series(dtype=bool)
            return scored

        scored = frame.copy()
        scored["outlier_score"] = 0.0
        scored["is_outlier"] = False
        return scored


def build_placeholder_models() -> PlaceholderModelBundle:
    return PlaceholderModelBundle(
        classifier=PlaceholderTransactionClassifier(),
        outlier_detector=PlaceholderOutlierDetector(),
    )
