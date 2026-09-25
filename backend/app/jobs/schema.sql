CREATE TABLE IF NOT EXISTS analysis_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    repository_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL,
    idempotency_hash text NOT NULL,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL CHECK (max_attempts BETWEEN 1 AND 20),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_until timestamptz,
    claim_token uuid,
    cancel_requested boolean NOT NULL DEFAULT false,
    error_code text,
    result_analysis_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (snapshot_id, repository_id)
        REFERENCES repository_snapshots(id, repository_id) ON DELETE CASCADE,
    UNIQUE (user_id, idempotency_hash),
    CHECK ((status = 'running') = (claim_token IS NOT NULL AND lease_until IS NOT NULL)),
    CHECK (status <> 'completed' OR result_analysis_id IS NOT NULL)
);

-- Existing installations have the original five-state check. Replace only
-- that check so a partial terminal result can be recorded without dropping
-- jobs or changing their ownership/snapshot data.
ALTER TABLE analysis_jobs DROP CONSTRAINT IF EXISTS analysis_jobs_status_check;
ALTER TABLE analysis_jobs ADD CONSTRAINT analysis_jobs_status_check
    CHECK (status IN ('queued', 'running', 'completed', 'partial', 'failed', 'cancelled'));
ALTER TABLE analysis_jobs DROP CONSTRAINT IF EXISTS analysis_jobs_partial_result_check;
ALTER TABLE analysis_jobs ADD CONSTRAINT analysis_jobs_partial_result_check
    CHECK (status <> 'partial' OR result_analysis_id IS NOT NULL);

CREATE INDEX IF NOT EXISTS analysis_jobs_claimable
    ON analysis_jobs (available_at, created_at)
    WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS analysis_jobs_expired
    ON analysis_jobs (lease_until)
    WHERE status = 'running';
