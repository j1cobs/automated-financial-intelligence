from __future__ import annotations

import logging
import re
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

LOGGER = logging.getLogger(__name__)

RULES = {
    r"(?i)(uber|lyft|taxi|transit)": "transport",
    r"(?i)(whole foods|trader joe|grocery|market)": "groceries",
    r"(?i)(rent|mortgage)": "housing",
    r"(?i)(netflix|spotify|hulu|disney)": "subscriptions",
    r"(?i)(atm|withdrawal|cash)": "cash",
}


class TransactionClassifier:
    def __init__(self, model_path: str) -> None:
        self.model_path = Path(model_path)
        self.model: Pipeline | None = None

    def train(self, labeled_csv_path: str) -> Pipeline:
        frame = pd.read_csv(labeled_csv_path)
        required = {"description", "category"}
        missing = required.difference(set(frame.columns.str.lower()))
        if missing:
            raise ValueError(f"Missing required columns in labeled dataset: {sorted(missing)}")

        frame.columns = [column.lower() for column in frame.columns]
        frame = frame.dropna(subset=["description", "category"])
        if frame.empty:
            raise ValueError("Labeled dataset has no trainable rows")

        pipeline: Pipeline = Pipeline(
            [
                ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
                ("clf", LinearSVC(random_state=42)),
            ]
        )
        pipeline.fit(frame["description"].astype(str), frame["category"].astype(str))

        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(pipeline, self.model_path)
        self.model = pipeline
        LOGGER.info("Trained classifier and saved model to %s", self.model_path)
        return pipeline

    def _rule_based_category(self, description: str) -> str:
        for pattern, category in RULES.items():
            if re.search(pattern, description):
                return category
        return "uncategorized"

    def load(self) -> Pipeline | None:
        if self.model is not None:
            return self.model
        if self.model_path.exists():
            self.model = joblib.load(self.model_path)
            return self.model
        return None

    def categorize(self, descriptions: pd.Series) -> pd.Series:
        model = self.load()
        if model is None:
            LOGGER.warning("No model found. Falling back to rule-based categorization.")
            return descriptions.fillna("").astype(str).map(self._rule_based_category)
        return pd.Series(model.predict(descriptions.fillna("").astype(str)), index=descriptions.index)
