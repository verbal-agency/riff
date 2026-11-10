-- Model-written article notes and cross-source idea digests.

CREATE TABLE IF NOT EXISTS article_notes (
    evidence_id TEXT PRIMARY KEY REFERENCES evidence_versions(evidence_id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    note JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS digests (
    digest_id TEXT PRIMARY KEY,
    run_date DATE NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    model TEXT NOT NULL,
    article_count INTEGER NOT NULL CHECK (article_count >= 0),
    payload JSONB NOT NULL,
    markdown TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS digests_run_date_idx ON digests (run_date DESC, created_at DESC);
