-- G36 deterministic project deltas, personalized guidance, and feedback memory.

CREATE TABLE github_guidance_deltas (
    delta_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES github_project_inventory(project_id),
    monitor_run_id TEXT REFERENCES github_monitor_runs(monitor_run_id),
    current_snapshot_id TEXT NOT NULL REFERENCES github_project_snapshots(snapshot_id),
    previous_snapshot_id TEXT REFERENCES github_project_snapshots(snapshot_id),
    status TEXT NOT NULL CHECK (status IN ('NEW', 'CHANGED', 'UNCHANGED', 'DUPLICATE', 'UNAVAILABLE')),
    claims JSONB NOT NULL,
    source_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    uncertainty JSONB NOT NULL DEFAULT '[]'::jsonb,
    parser_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL UNIQUE CHECK (length(trim(input_fingerprint)) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_origin TEXT NOT NULL DEFAULT 'LIVE',
    origin_owner TEXT,
    origin_policy_version TEXT NOT NULL DEFAULT 'governance-v1'
);

CREATE INDEX github_guidance_deltas_project_idx ON github_guidance_deltas (project_id, created_at DESC);

CREATE TABLE github_guidance_versions (
    guidance_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES github_project_inventory(project_id),
    delta_id TEXT NOT NULL REFERENCES github_guidance_deltas(delta_id),
    prior_guidance_id TEXT REFERENCES github_guidance_versions(guidance_id),
    version INTEGER NOT NULL CHECK (version >= 1),
    actions JSONB NOT NULL,
    rationale TEXT NOT NULL,
    cited_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    uncertainty JSONB NOT NULL DEFAULT '[]'::jsonb,
    policy_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL UNIQUE CHECK (length(trim(input_fingerprint)) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_origin TEXT NOT NULL DEFAULT 'LIVE',
    origin_owner TEXT,
    origin_policy_version TEXT NOT NULL DEFAULT 'governance-v1'
);

CREATE INDEX github_guidance_versions_project_idx ON github_guidance_versions (project_id, version DESC);

CREATE TABLE github_guidance_feedback (
    feedback_id TEXT PRIMARY KEY,
    guidance_id TEXT NOT NULL REFERENCES github_guidance_versions(guidance_id),
    decision TEXT NOT NULL CHECK (decision IN ('ACCEPTED', 'REJECTED', 'DEFERRED', 'CORRECTED')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    correction JSONB NOT NULL DEFAULT '{}'::jsonb,
    actor TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX github_guidance_feedback_guidance_idx ON github_guidance_feedback (guidance_id, created_at DESC);
