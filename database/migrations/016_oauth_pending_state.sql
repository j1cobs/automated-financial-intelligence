-- PKCE pending-state storage for the FastAPI OAuth flow (api/), replacing the in-process
-- dict (`app/auth.py::_google_oauth_pending_sessions`) that only worked because Streamlit
-- runs as a single long-lived process. The API may run multiple workers/restart between the
-- sign-in click and the callback, so the state has to live somewhere shared.
CREATE TABLE IF NOT EXISTS oauth_pending_state (
    state TEXT PRIMARY KEY,
    code_verifier TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth_pending_state_created_at ON oauth_pending_state(created_at);
