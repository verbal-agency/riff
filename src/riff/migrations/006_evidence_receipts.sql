-- G05 compact, versioned Evidence Receipts and processing attempts.

CREATE TABLE evidence_receipts (
    receipt_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence_versions(evidence_id),
    content_hash TEXT NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    extractor_version TEXT NOT NULL CHECK (length(trim(extractor_version)) > 0),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    status TEXT NOT NULL CHECK (status IN ('SUCCEEDED', 'FAILED_VALIDATION', 'FAILED_TRANSIENT', 'SKIPPED_CACHED')),
    summary TEXT NOT NULL,
    relevant_spans JSONB NOT NULL,
    capability_candidates JSONB NOT NULL,
    technology_candidates JSONB NOT NULL,
    claims JSONB NOT NULL,
    signal_strength JSONB NOT NULL,
    source_metadata JSONB NOT NULL,
    uncertainty JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (evidence_id, content_hash, extractor_version)
);

CREATE TABLE receipt_attempts (
    attempt_id TEXT PRIMARY KEY,
    evidence_id TEXT NOT NULL REFERENCES evidence_versions(evidence_id),
    content_hash TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    prompt_schema_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'FAILED_VALIDATION', 'FAILED_TRANSIENT', 'SKIPPED_CACHED')),
    error_code TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    UNIQUE (attempt_id)
);

CREATE INDEX evidence_receipts_evidence_idx ON evidence_receipts (evidence_id, created_at DESC);
CREATE INDEX evidence_receipts_status_idx ON evidence_receipts (status, created_at);
CREATE INDEX receipt_attempts_pending_idx ON receipt_attempts (status, started_at);
