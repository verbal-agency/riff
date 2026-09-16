-- G34 explicit GitHub repository watches and bounded quantitative discovery.

CREATE TABLE github_repository_watches (
    watch_id TEXT PRIMARY KEY,
    provider_repository_id TEXT NOT NULL UNIQUE REFERENCES github_repositories(provider_repository_id),
    project_id TEXT REFERENCES github_project_inventory(project_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DISABLED', 'REVOKED')),
    scope JSONB NOT NULL DEFAULT '{}'::jsonb,
    cadence_seconds INTEGER NOT NULL CHECK (cadence_seconds >= 60),
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    last_run_id TEXT,
    last_success_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX github_repository_watches_status_idx ON github_repository_watches (status);

CREATE TABLE github_monitor_runs (
    monitor_run_id TEXT PRIMARY KEY,
    watch_id TEXT NOT NULL REFERENCES github_repository_watches(watch_id),
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED', 'SKIPPED')),
    policy_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL CHECK (length(trim(input_fingerprint)) = 64),
    collection_run_id TEXT REFERENCES collection_runs(run_id),
    project_snapshot_id TEXT REFERENCES github_project_snapshots(snapshot_id),
    stored_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    cursor_before JSONB NOT NULL DEFAULT '{}'::jsonb,
    cursor_after JSONB NOT NULL DEFAULT '{}'::jsonb,
    error JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX github_monitor_runs_watch_idx ON github_monitor_runs (watch_id, started_at DESC);

CREATE TABLE github_discovery_runs (
    discovery_run_id TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL CHECK (length(trim(input_fingerprint)) = 64),
    request_count INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER NOT NULL DEFAULT 0,
    candidate_count INTEGER NOT NULL DEFAULT 0,
    threshold_evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE github_discovery_candidates (
    candidate_id TEXT PRIMARY KEY,
    discovery_run_id TEXT NOT NULL REFERENCES github_discovery_runs(discovery_run_id),
    provider_repository_id TEXT NOT NULL,
    full_name TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK (disposition IN ('AUTO_QUEUED', 'DISABLED_SCOPE_PROPOSED', 'APPROVED', 'REJECTED', 'PROMOTED')),
    rule_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    root_id TEXT,
    correlation_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    threshold_evaluation JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    uncertainty JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (discovery_run_id, provider_repository_id)
);

CREATE INDEX github_discovery_candidates_disposition_idx ON github_discovery_candidates (disposition, created_at DESC);

CREATE TABLE github_watch_events (
    event_id TEXT PRIMARY KEY,
    watch_id TEXT NOT NULL REFERENCES github_repository_watches(watch_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('CREATED', 'DISABLED', 'REVOKED', 'RUN_REQUESTED', 'RUN_COMPLETED')),
    reason TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
