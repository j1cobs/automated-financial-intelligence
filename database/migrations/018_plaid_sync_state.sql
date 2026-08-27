-- token_fingerprint is sha256(access_token); the raw access token is NEVER stored here.
CREATE TABLE IF NOT EXISTS plaid_sync_state (
    token_fingerprint TEXT PRIMARY KEY,
    cursor            TEXT NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
