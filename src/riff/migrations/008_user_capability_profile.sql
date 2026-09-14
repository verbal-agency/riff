-- G07 privacy-aware user profile evidence and recomputable gap assessments.

CREATE TABLE profile_evidence (
    profile_evidence_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL REFERENCES capabilities(capability_id),
    evidence_level TEXT NOT NULL CHECK (evidence_level IN ('PUBLICLY_DEMONSTRATED', 'PROFESSIONALLY_DEMONSTRATED_PRIVATE', 'HANDS_ON_PERSONAL', 'STUDIED', 'CONCEPTUALLY_FAMILIAR', 'UNKNOWN')),
    visibility TEXT NOT NULL CHECK (visibility IN ('PUBLIC', 'PRIVATE')),
    origin TEXT NOT NULL CHECK (origin IN ('GITHUB', 'WEBSITE', 'EXPERIENCE_LEDGER', 'RIFF_ARTIFACT', 'MANUAL')),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    reference TEXT,
    observed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'ARCHIVED')),
    source_evidence_id TEXT REFERENCES evidence_versions(evidence_id),
    attestation_state TEXT NOT NULL CHECK (attestation_state IN ('USER_ATTESTED', 'EXTERNALLY_VERIFIED', 'UNVERIFIED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE experience_ledger (
    ledger_id TEXT PRIMARY KEY,
    profile_evidence_id TEXT NOT NULL UNIQUE REFERENCES profile_evidence(profile_evidence_id),
    entry_text TEXT NOT NULL CHECK (length(trim(entry_text)) > 0),
    employer_or_context TEXT,
    attestation_state TEXT NOT NULL CHECK (attestation_state = 'USER_ATTESTED'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE profile_history (
    event_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('CREATE', 'CORRECT', 'ARCHIVE', 'RESTORE', 'FEEDBACK')),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    before_state JSONB NOT NULL,
    after_state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gap_assessments (
    assessment_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL REFERENCES capabilities(capability_id),
    classification TEXT NOT NULL CHECK (classification IN ('KNOWLEDGE_GAP', 'IMPLEMENTATION_GAP', 'SIGNALING_GAP', 'EXPERIENCE_GAP', 'NO_MEANINGFUL_GAP', 'UNKNOWN')),
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    uncertainty JSONB NOT NULL,
    evidence_snapshot JSONB NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX profile_evidence_capability_idx ON profile_evidence (capability_id, status, visibility);
CREATE INDEX profile_evidence_source_idx ON profile_evidence (source_evidence_id);
CREATE INDEX profile_history_target_idx ON profile_history (target_id, created_at);
CREATE INDEX gap_assessments_capability_idx ON gap_assessments (capability_id, computed_at DESC);
