from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from core.config import ConfigError, enforce_tls, load_settings


class LoadSettingsTests(unittest.TestCase):
    def _load(self, env: dict) -> object:
        with patch("core.config.load_dotenv"), patch.dict(os.environ, env, clear=True):
            return load_settings()

    def test_database_url_required(self) -> None:
        with patch("core.config.load_dotenv"), patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                load_settings()

    def test_plaid_optional_at_load(self) -> None:
        settings = self._load({"DATABASE_URL": "postgresql://localhost/db"})
        self.assertIsNone(settings.plaid_client_id)
        self.assertIsNone(settings.plaid_secret)
        self.assertEqual(settings.plaid_access_tokens, [])
        self.assertEqual(settings.plaid_access_token_owners, [])

    def test_plaid_values_read(self) -> None:
        settings = self._load(
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "PLAID_CLIENT_ID": "client-id",
                "PLAID_SECRET": "secret",
                "PLAID_ACCESS_TOKENS": "t1,t2",
                "PLAID_ACCESS_TOKEN_OWNERS": "Alex,Sam",
            }
        )
        self.assertEqual(settings.plaid_client_id, "client-id")
        self.assertEqual(settings.plaid_secret, "secret")
        self.assertEqual(settings.plaid_access_tokens, ["t1", "t2"])
        self.assertEqual(settings.plaid_access_token_owners, ["Alex", "Sam"])

    def test_plaid_base_url_default(self) -> None:
        settings = self._load({"DATABASE_URL": "postgresql://localhost/db"})
        self.assertEqual(settings.plaid_base_url, "https://sandbox.plaid.com")

    def test_env_over_secrets_precedence(self) -> None:
        with (
            patch("core.config.load_dotenv"),
            patch(
                "core.config._load_secrets_file",
                return_value={"DATABASE_URL": "postgresql://localhost/from-secrets"},
            ),
            patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/from-env"}, clear=True),
        ):
            settings = load_settings()
        self.assertIn("from-env", settings.database_url)

    def test_google_allowed_emails_split(self) -> None:
        settings = self._load(
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "GOOGLE_ALLOWED_EMAILS": "a@b.com,c@d.com",
            }
        )
        self.assertEqual(settings.google_allowed_emails, ["a@b.com", "c@d.com"])

    def test_plaid_access_token_owners_split(self) -> None:
        settings = self._load(
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "PLAID_ACCESS_TOKEN_OWNERS": "Alex,Sam",
            }
        )
        self.assertEqual(settings.plaid_access_token_owners, ["Alex", "Sam"])

    def test_plaid_access_tokens_split(self) -> None:
        settings = self._load(
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "PLAID_ACCESS_TOKENS": "t1,t2",
            }
        )
        self.assertEqual(settings.plaid_access_tokens, ["t1", "t2"])

    def test_load_settings_applies_enforce_tls(self) -> None:
        settings = self._load({"DATABASE_URL": "postgresql://u:p@db.example.com/x"})
        self.assertIn("sslmode=require", settings.database_url)

    def test_seed_database_url_absent_by_default(self) -> None:
        settings = self._load({"DATABASE_URL": "postgresql://localhost/db"})
        self.assertIsNone(settings.seed_database_url)

    def test_seed_database_url_read_and_tls_enforced(self) -> None:
        settings = self._load(
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "SEED_DATABASE_URL": "postgresql://u:p@seed.example.com/x",
            }
        )
        self.assertIn("sslmode=require", settings.seed_database_url)

    def test_seed_database_url_localhost_no_tls(self) -> None:
        settings = self._load(
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "SEED_DATABASE_URL": "postgresql://u:p@127.0.0.1:5433/finance",
            }
        )
        self.assertEqual(settings.seed_database_url, "postgresql://u:p@127.0.0.1:5433/finance")

    def test_github_event_name_absent_by_default(self) -> None:
        settings = self._load({"DATABASE_URL": "postgresql://localhost/db"})
        self.assertIsNone(settings.github_event_name)

    def test_github_event_name_read_through(self) -> None:
        settings = self._load(
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "GITHUB_EVENT_NAME": "workflow_dispatch",
            }
        )
        self.assertEqual(settings.github_event_name, "workflow_dispatch")


class EnforceTlsTests(unittest.TestCase):
    def test_appends_sslmode_for_remote_host(self) -> None:
        result = enforce_tls("postgresql://u:p@db.example.com/x")
        self.assertTrue(result.endswith("?sslmode=require"))

    def test_skips_localhost(self) -> None:
        localhost_url = "postgresql://u:p@localhost:5433/x"
        loopback_url = "postgresql://u:p@127.0.0.1/x"
        self.assertEqual(enforce_tls(localhost_url), localhost_url)
        self.assertEqual(enforce_tls(loopback_url), loopback_url)

    def test_preserves_existing_sslmode(self) -> None:
        url = "postgresql://u:p@db.example.com/x?sslmode=verify-full"
        self.assertEqual(enforce_tls(url), url)

    def test_appends_with_ampersand(self) -> None:
        url = "postgresql://u:p@db.example.com/x?connect_timeout=10"
        result = enforce_tls(url)
        self.assertTrue(result.endswith("&sslmode=require"))


if __name__ == "__main__":
    unittest.main()
