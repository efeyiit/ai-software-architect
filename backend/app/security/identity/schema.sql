-- Apply after the base users table. OAuth secrets are always ciphertext.
CREATE TABLE IF NOT EXISTS oauth_pending_states (
    state_digest bytea PRIMARY KEY CHECK (octet_length(state_digest) = 32),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose text NOT NULL CHECK (purpose IN ('login', 'private')),
    verifier_ciphertext bytea NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS oauth_pending_states_expiry ON oauth_pending_states(expires_at);

CREATE TABLE IF NOT EXISTS oauth_login_attempts (
    state_digest bytea PRIMARY KEY CHECK (octet_length(state_digest) = 32),
    browser_digest bytea NOT NULL CHECK (octet_length(browser_digest) = 32),
    verifier_ciphertext bytea NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS oauth_login_attempts_expiry ON oauth_login_attempts(expires_at);

CREATE TABLE IF NOT EXISTS oauth_sessions (
    session_digest bytea PRIMARY KEY CHECK (octet_length(session_digest) = 32),
    user_id uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS oauth_sessions_expiry ON oauth_sessions(expires_at);

CREATE TABLE IF NOT EXISTS oauth_connections (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose text NOT NULL CHECK (purpose IN ('login', 'private')),
    github_id text NOT NULL,
    token_ciphertext bytea NOT NULL,
    refresh_ciphertext bytea,
    scopes text[] NOT NULL DEFAULT '{}',
    expires_at timestamptz,
    refresh_expires_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, purpose)
);
