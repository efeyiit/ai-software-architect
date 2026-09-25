-- Additive schema: install after database/schema.sql and jobs/schema.sql.
CREATE TABLE IF NOT EXISTS analysis_cache (
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repository_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    branch text NOT NULL CHECK (length(branch) BETWEEN 1 AND 255),
    commit_sha text NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    config_digest text NOT NULL CHECK (config_digest ~ '^[0-9a-f]{64}$'),
    model_version text NOT NULL CHECK (length(model_version) BETWEEN 1 AND 128),
    analysis_version text NOT NULL CHECK (length(analysis_version) BETWEEN 1 AND 128),
    analysis_id text NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, repository_id, branch, commit_sha,
                 config_digest, model_version, analysis_version)
);

CREATE INDEX IF NOT EXISTS analysis_cache_expiry ON analysis_cache (expires_at);
