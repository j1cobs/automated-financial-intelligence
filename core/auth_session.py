from __future__ import annotations

SESSION_TIMEOUT_SECONDS = 60 * 60


def is_session_expired(authenticated_at: float | None, now: float) -> bool:
    if authenticated_at is None:
        return True
    return (now - authenticated_at) >= SESSION_TIMEOUT_SECONDS
