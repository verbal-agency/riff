-- G26 user-approved GitHub project inventory and versioned bounded snapshots.

CREATE TABLE github_project_inventory (
    project_id TEXT PRIMARY KEY,
    provider_repository_id TEXT NOT NULL UNIQUE REFERENCES github_repositories(provider_repository_id),
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    purpose TEXT,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    visibility TEXT NOT NULL CHECK (visibility IN ('PUBLIC')),
    review_status TEXT NOT NULL CHECK (review_status IN ('APPROVED', 'ARCHIVED')),
    reviewed_by TEXT NOT NULL CHECK (length(trim(reviewed_by)) > 0),
    reviewed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    archived_at TIMESTAMPTZ
);

CREATE TABLE github_project_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES github_project_inventory(project_id),
    version INTEGER NOT NULL CHECK (version >= 1),
    retrieved_at TIMESTAMPTZ NOT NULL,
    parser_version TEXT NOT NULL CHECK (length(trim(parser_version)) > 0),
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    input_hash TEXT NOT NULL CHECK (length(trim(input_hash)) = 64),
    previous_snapshot_id TEXT REFERENCES github_project_snapshots(snapshot_id),
    source_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary JSONB NOT NULL,
    UNIQUE (project_id, version),
    UNIQUE (project_id, input_hash)
);

CREATE INDEX github_project_snapshots_project_idx ON github_project_snapshots (project_id, version DESC);
