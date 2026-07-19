from __future__ import annotations

import unittest

from core.google_oauth import (
    GoogleIdentity,
    build_authorization_url,
    is_authorized_identity,
)


class GoogleOAuthTests(unittest.TestCase):
    def test_allows_matching_email(self) -> None:
        identity = GoogleIdentity(
            email="you@example.com",
            name="You",
            picture=None,
            subject="sub-123",
            email_verified=True,
        )

        self.assertTrue(is_authorized_identity(identity, ["you@example.com"]))

    def test_blocks_non_matching_email(self) -> None:
        identity = GoogleIdentity(
            email="other@example.com",
            name="Other",
            picture=None,
            subject="sub-456",
            email_verified=True,
        )

        self.assertFalse(is_authorized_identity(identity, ["you@example.com"]))

    def test_blocks_unverified_email(self) -> None:
        identity = GoogleIdentity(
            email="you@example.com",
            name="You",
            picture=None,
            subject="sub-123",
            email_verified=False,
        )

        self.assertFalse(is_authorized_identity(identity, ["you@example.com"]))

    def test_builds_google_authorization_url(self) -> None:
        url = build_authorization_url(
            client_id="client-id",
            redirect_uri="http://localhost:8501/",
            state="state-token",
            code_challenge="challenge-token",
        )

        self.assertIn("accounts.google.com/o/oauth2/v2/auth", url)
        self.assertIn("client_id=client-id", url)
        self.assertIn("state=state-token", url)
        self.assertIn("code_challenge=challenge-token", url)


if __name__ == "__main__":
    unittest.main()
