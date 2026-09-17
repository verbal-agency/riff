-- G37 first-class, versioned project-goal projections and append-only decisions.
CREATE TABLE github_project_goal_versions (
    goal_version_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES github_project_inventory(project_id),
    snapshot_id TEXT REFERENCES github_project_snapshots(snapshot_id),
    goal_key TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    title TEXT NOT NULL CHECK (length(trim(title)) > 0),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE','COMPLETED','ARCHIVED','UNKNOWN')),
    evidence_status TEXT NOT NULL CHECK (evidence_status IN ('OBSERVED','INFERRED','UNKNOWN')),
    source_surface TEXT NOT NULL,
    source_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_urls JSONB NOT NULL DEFAULT '[]'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL,
    parser_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL CHECK (length(trim(input_fingerprint)) = 64),
    prior_goal_version_id TEXT REFERENCES github_project_goal_versions(goal_version_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, goal_key, version),
    UNIQUE (project_id, goal_key, input_fingerprint)
);
CREATE INDEX github_project_goal_versions_project_idx ON github_project_goal_versions (project_id, goal_key, version DESC);

CREATE TABLE github_project_goal_events (
    event_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES github_project_inventory(project_id),
    goal_version_id TEXT NOT NULL REFERENCES github_project_goal_versions(goal_version_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('PRIORITIZED','COMPLETED','ARCHIVED','CORRECTED','REACTIVATED')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX github_project_goal_events_goal_idx ON github_project_goal_events (goal_version_id, created_at DESC);
