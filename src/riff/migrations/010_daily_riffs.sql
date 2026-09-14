-- G09 bounded, evidence-backed daily Riff publication.

CREATE TABLE daily_riff_runs (
    daily_run_id TEXT PRIMARY KEY,
    run_date DATE NOT NULL,
    generation_policy_version TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('COMPLETED', 'EMPTY', 'FAILED')),
    empty_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_date, generation_policy_version, input_fingerprint)
);

CREATE TABLE riffs (
    riff_id TEXT PRIMARY KEY,
    daily_run_id TEXT NOT NULL REFERENCES daily_riff_runs(daily_run_id),
    rank INTEGER NOT NULL CHECK (rank > 0 AND rank <= 3),
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'PUBLISHED', 'REJECTED', 'SKIPPED')),
    observation TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    why_now TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    user_relevance TEXT NOT NULL,
    underlying_capability TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    strongest_counterargument TEXT NOT NULL,
    alternative_explanation TEXT NOT NULL,
    falsification_conditions JSONB NOT NULL,
    associated_technologies JSONB NOT NULL,
    supporting_receipt_ids JSONB NOT NULL,
    counter_receipt_ids JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (daily_run_id, rank)
);

CREATE TABLE riff_citations (
    citation_id TEXT PRIMARY KEY,
    riff_id TEXT NOT NULL REFERENCES riffs(riff_id),
    receipt_id TEXT NOT NULL REFERENCES evidence_receipts(receipt_id),
    claim_type TEXT NOT NULL CHECK (claim_type IN ('OBSERVATION', 'HYPOTHESIS', 'RECOMMENDATION', 'COUNTEREVIDENCE')),
    statement TEXT NOT NULL,
    UNIQUE (riff_id, receipt_id, claim_type, statement)
);

CREATE TABLE riff_contexts (
    context_id TEXT PRIMARY KEY,
    daily_run_id TEXT NOT NULL REFERENCES daily_riff_runs(daily_run_id),
    candidate_id TEXT NOT NULL,
    receipt_ids JSONB NOT NULL,
    profile_slice JSONB NOT NULL,
    decision_ids JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (daily_run_id, candidate_id)
);

CREATE INDEX riffs_daily_run_rank_idx ON riffs (daily_run_id, rank);
CREATE INDEX riff_citations_riff_idx ON riff_citations (riff_id);
