-- G08 deterministic candidate-signal ranking and explanations.

CREATE TABLE rank_configs (
    config_version TEXT PRIMARY KEY,
    weights JSONB NOT NULL,
    min_source_types INTEGER NOT NULL CHECK (min_source_types >= 1),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE rank_runs (
    rank_run_id TEXT PRIMARY KEY,
    config_version TEXT NOT NULL REFERENCES rank_configs(config_version),
    input_fingerprint TEXT NOT NULL UNIQUE,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE correlation_groups (
    group_id TEXT PRIMARY KEY,
    rank_run_id TEXT NOT NULL REFERENCES rank_runs(rank_run_id),
    root_source TEXT NOT NULL,
    UNIQUE (rank_run_id, root_source)
);

CREATE TABLE correlation_members (
    group_id TEXT NOT NULL REFERENCES correlation_groups(group_id),
    evidence_id TEXT NOT NULL REFERENCES evidence_versions(evidence_id),
    PRIMARY KEY (group_id, evidence_id)
);

CREATE TABLE candidate_signals (
    signal_id TEXT PRIMARY KEY,
    rank_run_id TEXT NOT NULL REFERENCES rank_runs(rank_run_id),
    capability_id TEXT NOT NULL REFERENCES capabilities(capability_id),
    classification TEXT NOT NULL CHECK (classification IN ('TREND_CANDIDATE', 'OBSERVATION', 'INSUFFICIENT_TREND_EVIDENCE')),
    rank INTEGER NOT NULL CHECK (rank > 0),
    score NUMERIC(10,6) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    UNIQUE (rank_run_id, capability_id)
);

CREATE TABLE signal_features (
    signal_id TEXT PRIMARY KEY REFERENCES candidate_signals(signal_id),
    features JSONB NOT NULL
);

CREATE TABLE signal_explanations (
    signal_id TEXT PRIMARY KEY REFERENCES candidate_signals(signal_id),
    weights JSONB NOT NULL,
    contributions JSONB NOT NULL,
    eligibility_reason TEXT NOT NULL
);

CREATE INDEX candidate_signals_rank_idx ON candidate_signals (rank_run_id, rank);
CREATE INDEX signal_features_signal_idx ON signal_features (signal_id);
