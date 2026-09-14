-- G10 explicit user decisions, lifecycle history, and resurfacing memory.

ALTER TABLE riffs DROP CONSTRAINT IF EXISTS riffs_status_check;
ALTER TABLE riffs ADD CONSTRAINT riffs_status_check CHECK (status IN ('DRAFT', 'PUBLISHED', 'REJECTED', 'SKIPPED', 'NEW', 'WATCHING', 'EXPLORING', 'ARCHIVED'));
ALTER TABLE riffs ADD COLUMN candidate_id TEXT;

CREATE TABLE riff_decisions (
    decision_id TEXT PRIMARY KEY,
    riff_id TEXT NOT NULL REFERENCES riffs(riff_id),
    decision TEXT NOT NULL CHECK (decision IN ('WATCH', 'REJECT', 'ARCHIVE', 'APPROVE_EXPLORATION', 'CONFIRM_PROFILE_UPDATE', 'CORRECT')),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    actor_kind TEXT NOT NULL CHECK (actor_kind IN ('USER', 'MODEL', 'SYSTEM')),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    structured_reason JSONB NOT NULL,
    semantic_implications JSONB NOT NULL,
    evidence_snapshot JSONB NOT NULL,
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    supersedes_decision_id TEXT REFERENCES riff_decisions(decision_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE riff_status_history (
    transition_id TEXT PRIMARY KEY,
    riff_id TEXT NOT NULL REFERENCES riffs(riff_id),
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    decision_id TEXT NOT NULL REFERENCES riff_decisions(decision_id),
    actor TEXT NOT NULL,
    actor_kind TEXT NOT NULL CHECK (actor_kind IN ('USER', 'MODEL', 'SYSTEM')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE riff_resurface_events (
    resurface_id TEXT PRIMARY KEY,
    riff_id TEXT NOT NULL REFERENCES riffs(riff_id),
    previous_decision_id TEXT NOT NULL REFERENCES riff_decisions(decision_id),
    new_receipt_ids JSONB NOT NULL,
    explanation TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX riff_decisions_riff_idx ON riff_decisions (riff_id, created_at DESC);
CREATE INDEX riff_status_history_riff_idx ON riff_status_history (riff_id, created_at);
