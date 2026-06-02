from __future__ import annotations

import unittest

from core.auth_session import SESSION_TIMEOUT_SECONDS, is_session_expired


class AuthSessionTests(unittest.TestCase):
    def test_session_is_expired_when_window_is_exceeded(self) -> None:
        self.assertTrue(is_session_expired(100.0, 100.0 + SESSION_TIMEOUT_SECONDS + 1))

    def test_session_is_active_within_window(self) -> None:
        self.assertFalse(is_session_expired(100.0, 100.0 + SESSION_TIMEOUT_SECONDS - 1))


if __name__ == "__main__":
    unittest.main()
