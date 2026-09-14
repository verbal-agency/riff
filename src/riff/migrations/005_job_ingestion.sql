-- G04 bounded job-market import and reversible employer identity state.

CREATE TABLE job_employers (
    employer_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    provider_employer_id TEXT,
    display_name TEXT NOT NULL CHECK (length(trim(display_name)) > 0),
    normalized_name TEXT NOT NULL CHECK (length(trim(normalized_name)) > 0),
    identity_state TEXT NOT NULL CHECK (identity_state IN ('CONFIDENT', 'AMBIGUOUS')),
    confidence NUMERIC CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX job_employers_confident_key_uq
    ON job_employers (source_id, normalized_name)
    WHERE identity_state = 'CONFIDENT' AND provider_employer_id IS NULL;

CREATE TABLE job_employer_aliases (
    alias_id TEXT PRIMARY KEY,
    employer_id TEXT NOT NULL REFERENCES job_employers(employer_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    alias TEXT NOT NULL CHECK (length(trim(alias)) > 0),
    normalized_alias TEXT NOT NULL CHECK (length(trim(normalized_alias)) > 0),
    status TEXT NOT NULL CHECK (status IN ('CONFIRMED', 'CANDIDATE')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (employer_id, normalized_alias)
);

CREATE TABLE job_postings (
    evidence_id TEXT PRIMARY KEY REFERENCES evidence_versions(evidence_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    provider_posting_id TEXT,
    canonical_url TEXT NOT NULL,
    employer_id TEXT REFERENCES job_employers(employer_id),
    employer_display_name TEXT,
    role_title TEXT NOT NULL,
    seniority TEXT,
    compensation TEXT,
    location TEXT,
    published_at TIMESTAMPTZ,
    observed_at TIMESTAMPTZ NOT NULL,
    expired BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX job_postings_source_provider_idx ON job_postings (source_id, provider_posting_id);
CREATE INDEX job_postings_employer_idx ON job_postings (employer_id);
CREATE INDEX job_postings_role_idx ON job_postings (role_title);
CREATE INDEX job_postings_published_idx ON job_postings (published_at);
