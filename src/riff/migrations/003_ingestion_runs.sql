-- G02 incremental source configuration and collection-run state.

CREATE TABLE ingestion_source_configs (
    source_id TEXT PRIMARY KEY REFERENCES sources(source_id),
    endpoint TEXT NOT NULL CHECK (endpoint ~* '^https?://'),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    config_version INTEGER NOT NULL CHECK (config_version >= 1),
    cursor_kind TEXT NOT NULL CHECK (length(trim(cursor_kind)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE collection_cursors (
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    cursor_kind TEXT NOT NULL,
    cursor_value TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, cursor_kind)
);

CREATE TABLE collection_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'PARTIAL', 'FAILED')),
    source_ids JSONB NOT NULL,
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    CHECK ((status = 'RUNNING' AND finished_at IS NULL) OR (status <> 'RUNNING' AND finished_at IS NOT NULL))
);

CREATE TABLE collection_item_results (
    item_result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES collection_runs(run_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    canonical_url TEXT,
    source_native_id TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('STORED', 'DUPLICATE', 'SKIPPED', 'FAILED_TRANSIENT', 'FAILED_PERMANENT')),
    evidence_id TEXT REFERENCES evidence_versions(evidence_id),
    error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((outcome IN ('STORED', 'DUPLICATE') AND evidence_id IS NOT NULL)
        OR (outcome IN ('SKIPPED', 'FAILED_TRANSIENT', 'FAILED_PERMANENT') AND evidence_id IS NULL))
);

CREATE INDEX collection_item_results_run_idx ON collection_item_results (run_id);
CREATE INDEX collection_item_results_source_idx ON collection_item_results (source_id, created_at);
