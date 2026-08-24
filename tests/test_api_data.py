from __future__ import annotations

import os
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/db")

import jwt as pyjwt  # noqa: E402
import pandas as pd  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.deps import get_db, get_settings  # noqa: E402
from api.main import app  # noqa: E402
from api.security import COOKIE_NAME  # noqa: E402
from core.config import Settings  # noqa: E402


def _settings(**overrides) -> Settings:
    base = dict(
        supabase_url=None,
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        google_oauth_redirect_uri="http://localhost:8000/auth/google/callback",
        google_allowed_emails=["you@example.com"],
        plaid_client_id=None,
        plaid_secret=None,
        plaid_access_tokens=[],
        plaid_access_token_owners=[],
        plaid_base_url="https://sandbox.plaid.com",
        database_url="postgresql://localhost/db",
        seed_database_url=None,
        github_event_name=None,
        model_path="artifacts/classifier.joblib",
        labeled_dataset_path="labeled_transactions.csv",
        jwt_secret="test-secret",
        frontend_origin="https://example.vercel.app",
    )
    base.update(overrides)
    return Settings(**base)


def _tx_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2026-08-01"),
                "transaction_hash": "hash-1",
                "account_key": "plaid:acc1",
                "account_name": "Checking",
                "owner_name": "Alex",
                "account_type": "depository",
                "account_subtype": "checking",
                "description": "Employer Payroll",
                "amount": -1000.0,
                "category": "Income",
                "outlier_score": 0.1,
                "is_outlier": False,
                "is_recurring": True,
                "is_duplicate": False,
            },
            {
                "date": pd.Timestamp("2026-08-02"),
                "transaction_hash": "hash-2",
                "account_key": "plaid:acc1",
                "account_name": "Checking",
                "owner_name": "Alex",
                "account_type": "depository",
                "account_subtype": "checking",
                "description": "Weird Purchase",
                "amount": 500.0,
                "category": "Shopping",
                "outlier_score": 0.95,
                "is_outlier": True,
                "is_recurring": False,
                "is_duplicate": False,
            },
        ]
    )


def _empty_tx_df() -> pd.DataFrame:
    return _tx_df().iloc[0:0]


def _acct_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "account_key": "plaid:acc1",
                "account_name": "Checking",
                "official_name": "Alex Chequing",
                "mask": "1234",
                "owner_name": "Alex",
                "account_type": "depository",
                "account_subtype": "checking",
                "balance_available": 1000.0,
                "balance_current": 1000.0,
                "balance_limit": None,
                "manual_credit_limit": None,
                "iso_currency_code": "CAD",
                "updated_at": pd.Timestamp.now(tz="UTC"),
            }
        ]
    )


class ApiDataTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = _settings()
        self.mock_db = MagicMock()
        self.mock_db.database_url = self.settings.database_url
        self.mock_db.get_categories.return_value = ["Groceries", "Income", "Shopping"]
        self.mock_db.get_budgets.return_value = [{"category": "Shopping", "monthly_limit": 200.0}]
        app.dependency_overrides[get_settings] = lambda: self.settings
        app.dependency_overrides[get_db] = lambda: self.mock_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def _mint(self, **claim_overrides) -> str:
        payload = {
            "email": "you@example.com",
            "name": "You",
            "picture": None,
            "csrf": "csrf-token-value",
            "exp": time.time() + 3600,
            "iat": time.time(),
        }
        payload.update(claim_overrides)
        return pyjwt.encode(payload, self.settings.jwt_secret, algorithm="HS256")

    def _authed_client(self) -> TestClient:
        token = self._mint()
        self.client.cookies.set(COOKIE_NAME, token)
        return self.client

    def _load_financial_data_patch(self, tx_df=None, acct_df=None):
        return patch(
            "api.routers.data.load_financial_data",
            return_value=(
                tx_df if tx_df is not None else _tx_df(),
                acct_df if acct_df is not None else _acct_df(),
            ),
        )


READ_ENDPOINTS = [
    "/overview",
    "/cash-flow",
    "/budget",
    "/ledger",
    "/anomalies",
    "/categories",
    "/filter-options",
]

WRITE_ENDPOINTS = [
    ("patch", "/accounts/plaid:acc1/credit-limit", {"limit": 500.0}),
    ("put", "/budgets/Shopping", {"monthly_limit": 300.0}),
    ("patch", "/transactions/hash-2/category", {"category": "Groceries"}),
    ("patch", "/transactions/hash-2/recurring", {"recurring": True}),
    ("patch", "/transactions/hash-2/duplicate", {"duplicate": True}),
]


class UnauthenticatedTests(ApiDataTestCase):
    def test_read_endpoints_require_auth(self) -> None:
        with self._load_financial_data_patch():
            for path in READ_ENDPOINTS:
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 401)

    def test_write_endpoints_require_auth(self) -> None:
        for method, path, body in WRITE_ENDPOINTS:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, json=body)
                self.assertEqual(response.status_code, 401)


class CsrfTests(ApiDataTestCase):
    def test_missing_csrf_header_returns_403(self) -> None:
        self._authed_client()
        for method, path, body in WRITE_ENDPOINTS:
            with self.subTest(path=path):
                response = getattr(self.client, method)(path, json=body)
                self.assertEqual(response.status_code, 403)

    def test_wrong_csrf_header_returns_403(self) -> None:
        self._authed_client()
        for method, path, body in WRITE_ENDPOINTS:
            with self.subTest(path=path):
                response = getattr(self.client, method)(
                    path, json=body, headers={"X-CSRF-Token": "not-the-right-token"}
                )
                self.assertEqual(response.status_code, 403)

    def test_correct_csrf_header_succeeds(self) -> None:
        self._authed_client()
        for method, path, body in WRITE_ENDPOINTS:
            with self.subTest(path=path):
                response = getattr(self.client, method)(
                    path, json=body, headers={"X-CSRF-Token": "csrf-token-value"}
                )
                self.assertEqual(response.status_code, 204)


class WriteEndpointDbCallTests(ApiDataTestCase):
    def _headers(self) -> dict:
        self._authed_client()
        return {"X-CSRF-Token": "csrf-token-value"}

    def test_credit_limit_calls_set_manual_credit_limit(self) -> None:
        response = self.client.patch(
            "/accounts/plaid:acc1/credit-limit", json={"limit": 750.5}, headers=self._headers()
        )
        self.assertEqual(response.status_code, 204)
        self.mock_db.set_manual_credit_limit.assert_called_once_with("plaid:acc1", 750.5)

    def test_credit_limit_null_clears_limit(self) -> None:
        response = self.client.patch(
            "/accounts/plaid:acc1/credit-limit", json={"limit": None}, headers=self._headers()
        )
        self.assertEqual(response.status_code, 204)
        self.mock_db.set_manual_credit_limit.assert_called_once_with("plaid:acc1", None)

    def test_budget_calls_upsert_budget(self) -> None:
        response = self.client.put(
            "/budgets/Shopping", json={"monthly_limit": 300.0}, headers=self._headers()
        )
        self.assertEqual(response.status_code, 204)
        self.mock_db.upsert_budget.assert_called_once_with("Shopping", 300.0)

    def test_category_calls_update_transaction_category(self) -> None:
        response = self.client.patch(
            "/transactions/hash-2/category", json={"category": "Groceries"}, headers=self._headers()
        )
        self.assertEqual(response.status_code, 204)
        self.mock_db.update_transaction_category.assert_called_once_with("hash-2", "Groceries")

    def test_recurring_calls_update_transaction_recurring(self) -> None:
        response = self.client.patch(
            "/transactions/hash-2/recurring", json={"recurring": True}, headers=self._headers()
        )
        self.assertEqual(response.status_code, 204)
        self.mock_db.update_transaction_recurring.assert_called_once_with("hash-2", True)

    def test_duplicate_calls_update_transaction_duplicate(self) -> None:
        response = self.client.patch(
            "/transactions/hash-2/duplicate", json={"duplicate": True}, headers=self._headers()
        )
        self.assertEqual(response.status_code, 204)
        self.mock_db.update_transaction_duplicate.assert_called_once_with("hash-2", True)


class ReadEndpointShapeTests(ApiDataTestCase):
    def test_overview_shape_and_computation(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch():
            response = self.client.get("/overview")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("net_worth", body)
        self.assertIn("overview", body)
        self.assertEqual(body["net_worth"]["total_assets"], 1000.0)
        self.assertEqual(body["net_worth"]["total_liabilities"], 0.0)
        # income row is -1000 (adjusted +1000), outlier purchase (+500 -> adjusted -500,
        # expense) is excluded from income; net income should reflect the payroll deposit.
        self.assertEqual(body["overview"]["income"], 1000.0)
        self.assertEqual(body["overview"]["flagged_count"], 1)

    def test_cash_flow_shape(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch():
            response = self.client.get("/cash-flow")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["income"], 1000.0)
        self.assertEqual(body["flagged_count"], 1)

    def test_budget_shape_uses_get_budgets(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch():
            response = self.client.get("/budget")
        self.assertEqual(response.status_code, 200)
        self.mock_db.get_budgets.assert_called()
        body = response.json()
        cats = {item["category"]: item for item in body["items"]}
        self.assertIn("Shopping", cats)
        self.assertEqual(cats["Shopping"]["limit"], 200.0)

    def test_ledger_includes_hash_and_all_rows(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch():
            response = self.client.get("/ledger")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        hashes = {tx["hash"] for tx in body["transactions"]}
        self.assertEqual(hashes, {"hash-1", "hash-2"})

    def test_anomalies_only_includes_outliers(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch():
            response = self.client.get("/anomalies")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["anomalies"]), 1)
        self.assertEqual(body["anomalies"][0]["description"], "Weird Purchase")

    def test_categories_is_thin_wrapper(self) -> None:
        self._authed_client()
        response = self.client.get("/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["categories"], ["Groceries", "Income", "Shopping"])

    def test_filter_options_lists_the_unfiltered_choices(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch():
            response = self.client.get("/filter-options")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["owners"], ["Alex"])
        self.assertIn("Checking", body["accounts"])
        self.assertEqual([m["key"] for m in body["months"]], ["2026-08"])

    def test_read_endpoints_accept_filter_query_params(self) -> None:
        self._authed_client()
        params = {"period": "all_time", "owners": ["Alex"], "search": "Payroll"}
        with self._load_financial_data_patch():
            for path in ["/overview", "/cash-flow", "/budget", "/ledger", "/anomalies"]:
                with self.subTest(path=path):
                    self.assertEqual(self.client.get(path, params=params).status_code, 200)

    def test_owner_filter_narrows_the_ledger(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch():
            everyone = self.client.get("/ledger", params={"period": "all_time"})
            nobody = self.client.get("/ledger", params={"period": "all_time", "owners": ["Nobody"]})
        self.assertEqual(len(everyone.json()["transactions"]), 2)
        self.assertEqual(nobody.json()["transactions"], [])

    def test_search_narrows_the_ledger(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch():
            response = self.client.get("/ledger", params={"period": "all_time", "search": "Weird"})
        rows = response.json()["transactions"]
        self.assertEqual([r["hash"] for r in rows], ["hash-2"])

    def test_empty_transactions_returns_empty_view_models(self) -> None:
        self._authed_client()
        with self._load_financial_data_patch(tx_df=_empty_tx_df()):
            overview = self.client.get("/overview")
            ledger = self.client.get("/ledger")
            anomalies = self.client.get("/anomalies")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(overview.json()["overview"]["income"], 0.0)
        self.assertEqual(ledger.json()["transactions"], [])
        self.assertEqual(anomalies.json()["anomalies"], [])


if __name__ == "__main__":
    unittest.main()
