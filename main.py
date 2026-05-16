from __future__ import annotations

import logging
from datetime import date, timedelta

from analytics.classifier import TransactionClassifier
from analytics.outlier_detector import OutlierDetector
from config import ConfigError, load_settings
from database.db import DatabaseClient
from ingestion.csv_ingestor import CSVIngestor
from ingestion.plaid_ingestor import PlaidIngestor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
LOGGER = logging.getLogger(__name__)


def _build_ingestor(settings):
    if settings.ingestion_source == "plaid":
        if not settings.plaid_client_id or not settings.plaid_secret:
            raise ConfigError("PLAID_CLIENT_ID and PLAID_SECRET are required when INGESTION_SOURCE=plaid")
        return PlaidIngestor(
            client_id=settings.plaid_client_id,
            secret=settings.plaid_secret,
            access_tokens=settings.plaid_access_tokens,
            base_url=settings.plaid_base_url,
        )
    return CSVIngestor(settings.csv_paths)


def run_pipeline(days_back: int = 90) -> None:
    settings = load_settings()

    end_date = date.today()
    start_date = end_date - timedelta(days=days_back)

    ingestor = _build_ingestor(settings)
    transactions = ingestor.fetch_transactions(start_date=start_date, end_date=end_date)
    if transactions.empty:
        LOGGER.info("No transactions fetched. Pipeline complete.")
        return

    classifier = TransactionClassifier(settings.model_path)
    try:
        classifier.load() or classifier.train(settings.labeled_dataset_path)
    except (FileNotFoundError, ValueError) as error:
        LOGGER.warning("Could not train/load classifier model: %s", error)

    transactions["category"] = classifier.categorize(transactions["description"])
    outlier_detector = OutlierDetector()
    transactions = outlier_detector.score(transactions)

    database = DatabaseClient(settings.database_url)
    database.ensure_schema()
    database.upsert_accounts(transactions)
    database.upsert_categories(transactions["category"].dropna().astype(str).tolist())
    database.upsert_transactions(transactions)
    LOGGER.info("Pipeline completed successfully")


if __name__ == "__main__":
    try:
        run_pipeline()
    except Exception:
        LOGGER.exception("Pipeline failed")
        raise
