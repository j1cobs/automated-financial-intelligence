from __future__ import annotations

import os
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("DATABASE_URL", "postgresql://localhost/db")

import jwt as pyjwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.deps import get_db, get_settings  # noqa: E402
from api.main import app  # noqa: E402
from api.security import COOKIE_NAME  # noqa: E402
from core.config import Settings  # noqa: E402
from core.google_oauth import GoogleIdentity  # noqa: E402


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


class ApiAuthTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = _settings()
        self.mock_db = MagicMock()
        app.dependency_overrides[get_settings] = lambda: self.settings
        app.dependency_overrides[get_db] = lambda: self.mock_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def _mint(self, **claim_overrides) -> str:
        payload = {
            "email": "you@example.com",
            "name": "You",
            "picture": "https://example.com/pic.png",
            "csrf": "csrf-token-value",
            "exp": time.time() + 3600,
            "iat": time.time(),
        }
        payload.update(claim_overrides)
        return pyjwt.encode(payload, self.settings.jwt_secret, algorithm="HS256")


class MeEndpointTests(ApiAuthTestCase):
    def test_no_cookie_returns_401(self) -> None:
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_expired_jwt_returns_401(self) -> None:
        token = self._mint(exp=time.time() - 10)
        self.client.cookies.set(COOKIE_NAME, token)
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_tampered_jwt_returns_401(self) -> None:
        # Flip a character in the middle of the payload segment (not the last character of
        # the whole token, which can land on a base64url "don't-care" padding bit and
        # sometimes decode to the same bytes -- that made this test flaky).
        token = self._mint()
        header, payload, signature = token.split(".")
        mid = len(payload) // 2
        flipped_char = "A" if payload[mid] != "A" else "B"
        tampered_payload = payload[:mid] + flipped_char + payload[mid + 1 :]
        tampered = f"{header}.{tampered_payload}.{signature}"
        self.client.cookies.set(COOKIE_NAME, tampered)
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_wrong_secret_returns_401(self) -> None:
        token = pyjwt.encode(
            {
                "email": "you@example.com",
                "name": "You",
                "picture": None,
                "csrf": "csrf-token-value",
                "exp": time.time() + 3600,
            },
            "some-other-secret",
            algorithm="HS256",
        )
        self.client.cookies.set(COOKIE_NAME, token)
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 401)

    def test_valid_jwt_returns_identity_and_csrf(self) -> None:
        token = self._mint()
        self.client.cookies.set(COOKIE_NAME, token)
        response = self.client.get("/auth/me")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["email"], "you@example.com")
        self.assertEqual(body["name"], "You")
        self.assertEqual(body["picture"], "https://example.com/pic.png")
        self.assertEqual(body["csrf_token"], "csrf-token-value")


class GoogleCallbackTests(ApiAuthTestCase):
    def _identity(self, email: str = "you@example.com", verified: bool = True) -> GoogleIdentity:
        return GoogleIdentity(
            email=email,
            name="You",
            picture="https://example.com/pic.png",
            subject="subject-123",
            email_verified=verified,
        )

    def test_non_allowlisted_email_redirects_without_cookie(self) -> None:
        self.mock_db.pop_pending_oauth_state.return_value = "verifier"
        with (
            patch("api.routers.auth.exchange_code", return_value={"access_token": "token"}),
            patch(
                "api.routers.auth.fetch_userinfo",
                return_value=self._identity(email="stranger@example.com"),
            ),
        ):
            response = self.client.get(
                "/auth/google/callback",
                params={"code": "auth-code", "state": "state-abc"},
                follow_redirects=False,
            )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn(COOKIE_NAME, response.cookies)
        self.assertTrue(response.headers["location"].startswith(self.settings.frontend_origin))
        self.assertIn("error=", response.headers["location"])

    def test_missing_pending_state_redirects_without_cookie(self) -> None:
        self.mock_db.pop_pending_oauth_state.return_value = None
        response = self.client.get(
            "/auth/google/callback",
            params={"code": "auth-code", "state": "unknown-state"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(COOKIE_NAME, response.cookies)

    def test_happy_path_sets_cookie_with_correct_flags_and_claims(self) -> None:
        self.mock_db.pop_pending_oauth_state.return_value = "verifier"
        with (
            patch("api.routers.auth.exchange_code", return_value={"access_token": "token"}) as exchange_code,
            patch("api.routers.auth.fetch_userinfo", return_value=self._identity()),
        ):
            response = self.client.get(
                "/auth/google/callback",
                params={"code": "auth-code", "state": "state-abc"},
                follow_redirects=False,
            )

        exchange_code.assert_called_once_with(
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="http://localhost:8000/auth/google/callback",
            code="auth-code",
            code_verifier="verifier",
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], self.settings.frontend_origin)

        set_cookie_header = response.headers.get("set-cookie", "")
        self.assertIn(f"{COOKIE_NAME}=", set_cookie_header)
        self.assertIn("HttpOnly", set_cookie_header)
        self.assertIn("Secure", set_cookie_header)
        self.assertIn("samesite=none", set_cookie_header.lower())

        token = response.cookies.get(COOKIE_NAME)
        claims = pyjwt.decode(token, self.settings.jwt_secret, algorithms=["HS256"])
        self.assertEqual(claims["email"], "you@example.com")
        self.assertEqual(claims["name"], "You")
        self.assertEqual(claims["picture"], "https://example.com/pic.png")
        self.assertIn("csrf", claims)
        self.assertIn("exp", claims)

    def test_upstream_failure_redirects_without_cookie(self) -> None:
        self.mock_db.pop_pending_oauth_state.return_value = "verifier"
        with patch("api.routers.auth.exchange_code", side_effect=RuntimeError("boom")):
            response = self.client.get(
                "/auth/google/callback",
                params={"code": "auth-code", "state": "state-abc"},
                follow_redirects=False,
            )
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(COOKIE_NAME, response.cookies)


class GoogleStartTests(ApiAuthTestCase):
    def test_redirects_to_google_and_stores_pending_state(self) -> None:
        response = self.client.get("/auth/google/start", follow_redirects=False)
        self.assertIn(response.status_code, (302, 307))
        self.assertIn("accounts.google.com", response.headers["location"])
        self.mock_db.store_pending_oauth_state.assert_called_once()
        args = self.mock_db.store_pending_oauth_state.call_args[0]
        self.assertEqual(len(args), 2)  # (state, code_verifier)


if __name__ == "__main__":
    unittest.main()
