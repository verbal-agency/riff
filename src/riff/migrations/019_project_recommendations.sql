-- G27 deterministic project-aware recommendations and targeted Exploration linkage.

ALTER TABLE explorations
    ADD COLUMN IF NOT EXISTS target_project_id TEXT REFERENCES github_project_inventory(project_id);

CREATE INDEX IF NOT EXISTS explorations_target_project_idx
    ON explorations (target_project_id);

CREATE TABLE IF NOT EXISTS project_recommendations (
    recommendation_id TEXT PRIMARY KEY,
    riff_id TEXT NOT NULL REFERENCES riffs(riff_id) ON DELETE CASCADE,
    project_id TEXT REFERENCES github_project_inventory(project_id),
    disposition TEXT NOT NULL CHECK (disposition IN ('EXTEND_EXISTING', 'START_NEW', 'NOT_NOW')),
    fit_score NUMERIC(5,4) NOT NULL CHECK (fit_score >= 0 AND fit_score <= 1),
    learning_value NUMERIC(5,4) NOT NULL CHECK (learning_value >= 0 AND learning_value <= 1),
    effort_hours NUMERIC(5,2) NOT NULL CHECK (effort_hours >= 4 AND effort_hours <= 20),
    scope_risk NUMERIC(5,4) NOT NULL CHECK (scope_risk >= 0 AND scope_risk <= 1),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    project_snapshot_id TEXT REFERENCES github_project_snapshots(snapshot_id),
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    uncertainty JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'OVERRIDDEN', 'ACCEPTED', 'DEFERRED')),
    extension_seam TEXT,
    project_name TEXT,
    signal_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    project_evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    override_disposition TEXT CHECK (override_disposition IS NULL OR override_disposition IN ('EXTEND_EXISTING', 'START_NEW', 'NOT_NOW')),
    override_reason TEXT,
    input_fingerprint TEXT NOT NULL UNIQUE CHECK (length(trim(input_fingerprint)) = 64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS project_recommendations_riff_idx
    ON project_recommendations (riff_id, created_at DESC);
