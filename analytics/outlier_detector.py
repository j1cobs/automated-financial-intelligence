from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


class OutlierDetector:
    def __init__(self, contamination: float = 0.03, min_group_size: int = 8) -> None:
        self.contamination = contamination
        self.min_group_size = min_group_size

    def score(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            frame["outlier_score"] = pd.Series(dtype=float)
            frame["is_outlier"] = pd.Series(dtype=bool)
            return frame

        scored = frame.copy()
        scored["outlier_score"] = 0.0
        scored["is_outlier"] = False

        for category, group in scored.groupby("category", dropna=False):
            group_index = group.index
            features = group[["amount"]].fillna(0.0).astype(float)
            if len(group) < self.min_group_size:
                values = features["amount"].to_numpy(dtype=float)
                std = np.std(values)
                if std == 0:
                    z_scores = np.zeros_like(values)
                else:
                    z_scores = np.abs((values - np.mean(values)) / std)
                scored.loc[group_index, "outlier_score"] = z_scores
                scored.loc[group_index, "is_outlier"] = z_scores > 3
                continue

            model = IsolationForest(
                contamination=self.contamination,
                random_state=42,
                n_estimators=200,
            )
            model.fit(features)
            anomaly_score = -model.score_samples(features)
            prediction = model.predict(features)
            scored.loc[group_index, "outlier_score"] = anomaly_score
            scored.loc[group_index, "is_outlier"] = prediction == -1

        return scored
