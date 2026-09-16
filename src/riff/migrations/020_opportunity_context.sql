-- G28 opportunity contexts, execution candidates, and riff lineage.
CREATE TABLE IF NOT EXISTS opportunities (
    opportunity_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    version INTEGER NOT NULL,
    input_hash TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    context JSONB NOT NULL,
    evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_url, version),
    UNIQUE (source_url, input_hash)
);

CREATE TABLE IF NOT EXISTS execution_candidates (
    candidate_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL REFERENCES opportunities(opportunity_id) ON DELETE CASCADE,
    parent_candidate_id TEXT REFERENCES execution_candidates(candidate_id) ON DELETE SET NULL,
    operation TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    input_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (opportunity_id, input_hash)
);

CREATE TABLE IF NOT EXISTS opportunity_selections (
    opportunity_id TEXT PRIMARY KEY REFERENCES opportunities(opportunity_id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES execution_candidates(candidate_id),
    reason TEXT NOT NULL,
    selected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
