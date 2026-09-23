CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE CHECK (length(email) > 0),
    password_hash text NOT NULL CHECK (length(password_hash) > 0),
    github_id text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS repositories (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    github_url text NOT NULL CHECK (length(github_url) > 0),
    name text NOT NULL CHECK (length(name) > 0),
    language text,
    framework text,
    status text NOT NULL DEFAULT 'pending',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, github_url)
);

CREATE TABLE IF NOT EXISTS repository_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    commit_sha text NOT NULL CHECK (commit_sha ~ '^[0-9a-f]{40}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (repository_id, commit_sha),
    UNIQUE (id, repository_id)
);

CREATE TABLE IF NOT EXISTS analyses (
    id text PRIMARY KEY,
    repository_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL,
    type text NOT NULL,
    result jsonb NOT NULL,
    severity text,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (snapshot_id, repository_id)
        REFERENCES repository_snapshots(id, repository_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS analyses_repository_created
    ON analyses (repository_id, created_at DESC);

CREATE TABLE IF NOT EXISTS repository_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL,
    path text NOT NULL,
    language text,
    size bigint CHECK (size >= 0),
    summary text,
    UNIQUE (snapshot_id, path),
    UNIQUE (id, repository_id, snapshot_id),
    FOREIGN KEY (snapshot_id, repository_id)
        REFERENCES repository_snapshots(id, repository_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS dependencies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL,
    source_file text NOT NULL,
    target_file text NOT NULL,
    dependency_type text NOT NULL,
    FOREIGN KEY (snapshot_id, repository_id)
        REFERENCES repository_snapshots(id, repository_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS code_issues (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    repository_id uuid NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL,
    file_id uuid NOT NULL,
    line_number integer NOT NULL CHECK (line_number > 0),
    issue_type text NOT NULL,
    severity text NOT NULL,
    description text NOT NULL,
    suggestion text,
    FOREIGN KEY (file_id, repository_id, snapshot_id)
        REFERENCES repository_files(id, repository_id, snapshot_id) ON DELETE CASCADE,
    FOREIGN KEY (snapshot_id, repository_id)
        REFERENCES repository_snapshots(id, repository_id) ON DELETE CASCADE
);
