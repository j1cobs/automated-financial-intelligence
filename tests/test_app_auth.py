from __future__ import annotations

import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app import auth
from core.google_oauth import GoogleIdentity


class FakeSessionState(dict):
    def __getattr__(self, name: str):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name: str, value):
        self[name] = value


class AppAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        auth._google_oauth_pending_sessions.clear()
        self.session_state = FakeSessionState()
        self.query_params = {}

        self.session_state.authenticated = False

        self.st_patcher = patch.object(
            auth,
            "st",
            SimpleNamespace(
                session_state=self.session_state,
                query_params=self.query_params,
                error=Mock(),
                warning=Mock(),
                title=Mock(),
                markdown=Mock(),
                html=Mock(),
                caption=Mock(),
                sidebar=SimpleNamespace(
                    caption=Mock(),
                    button=Mock(return_value=False),
                ),
                rerun=Mock(),
            ),
        )
        self.st_patcher.start()

        self.query_param_patcher = patch.object(
            auth,
            "query_param",
            side_effect=lambda name: {"code": "auth-code", "state": "oauth-state"}.get(
                name
            ),
        )
        self.query_param_patcher.start()

    def tearDown(self) -> None:
        self.query_param_patcher.stop()
        self.st_patcher.stop()
        auth._google_oauth_pending_sessions.clear()

    def test_start_google_sign_in_keeps_pkce_verifier_available_for_callback(
        self,
    ) -> None:
        settings = SimpleNamespace(
            google_oauth_client_id="client-id",
            google_oauth_redirect_uri="http://localhost:8501/",
        )

        with patch.object(
            auth, "generate_pkce_pair", return_value=("verifier", "challenge")
        ), patch.object(
            auth.secrets, "token_urlsafe", return_value="oauth-state"
        ), patch.object(
            auth, "build_authorization_url", return_value="https://example.com/auth"
        ) as build_url:
            url = auth.start_google_sign_in(settings)

        self.assertEqual(url, "https://example.com/auth")
        self.assertEqual(
            auth._google_oauth_pending_sessions["oauth-state"][0], "verifier"
        )
        build_url.assert_called_once_with(
            client_id="client-id",
            redirect_uri="http://localhost:8501/",
            state="oauth-state",
            code_challenge="challenge",
        )

    def test_consume_google_callback_uses_pending_session_after_redirect(self) -> None:
        auth._google_oauth_pending_sessions["oauth-state"] = ("verifier", time.time())

        settings = SimpleNamespace(
            google_oauth_client_id="client-id",
            google_oauth_client_secret="client-secret",
            google_oauth_redirect_uri="http://localhost:8501/",
            google_allowed_emails=["you@example.com"],
        )
        identity = GoogleIdentity(
            email="you@example.com",
            name="You",
            picture=None,
            subject="subject-123",
            email_verified=True,
        )

        with patch.object(
            auth, "exchange_code", return_value={"access_token": "access-token"}
        ) as exchange_code, patch.object(
            auth, "fetch_userinfo", return_value=identity
        ) as fetch_userinfo, patch.object(
            auth, "is_authorized_identity", return_value=True
        ) as is_authorized_identity:
            result = auth.consume_google_callback(settings)

        self.assertTrue(result)
        exchange_code.assert_called_once_with(
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="http://localhost:8501/",
            code="auth-code",
            code_verifier="verifier",
        )
        fetch_userinfo.assert_called_once_with("access-token")
        is_authorized_identity.assert_called_once_with(identity, ["you@example.com"])
        self.assertNotIn("oauth-state", auth._google_oauth_pending_sessions)
        auth.st.rerun.assert_called_once()
        auth.st.error.assert_not_called()

    def test_consume_google_callback_reports_expired_when_pending_session_is_missing(
        self,
    ) -> None:
        settings = SimpleNamespace(
            google_oauth_client_id="client-id",
            google_oauth_client_secret="client-secret",
            google_oauth_redirect_uri="http://localhost:8501/",
            google_allowed_emails=["you@example.com"],
        )

        result = auth.consume_google_callback(settings)

        self.assertFalse(result)
        auth.st.error.assert_called_once_with(
            "Google sign-in session expired. Please try again."
        )
        auth.st.rerun.assert_not_called()


if __name__ == "__main__":
    unittest.main()
