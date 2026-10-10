-- G41 worker leases, canonical reports, and append-only operational history.

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'unknown',
    ADD COLUMN IF NOT EXISTS lease_owner TEXT,
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS recovery_count INTEGER NOT NULL DEFAULT 0 CHECK (recovery_count >= 0),
    ADD COLUMN IF NOT EXISTS report_metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS pipeline_run_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    prior_lease_owner TEXT,
    lease_owner TEXT,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS pipeline_run_events_run_idx
    ON pipeline_run_events (run_id, event_id);
CREATE INDEX IF NOT EXISTS pipeline_runs_lease_idx
    ON pipeline_runs (status, lease_expires_at);
