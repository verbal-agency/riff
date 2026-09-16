-- G35 origin ownership, quarantine, and reviewable retention/cleanup plans.

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'sources', 'source_items', 'evidence_versions', 'retrievals',
        'collection_runs', 'daily_riff_runs', 'github_project_inventory',
        'github_project_snapshots', 'project_recommendations'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS data_origin TEXT NOT NULL DEFAULT ''UNCLASSIFIED''', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS origin_owner TEXT', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS origin_run_id TEXT', table_name);
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS origin_policy_version TEXT NOT NULL DEFAULT ''governance-v1''', table_name);
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I_data_origin_check', table_name, table_name);
        EXECUTE format('ALTER TABLE %I ADD CONSTRAINT %I_data_origin_check CHECK (data_origin IN (''LIVE'', ''FIXTURE'', ''TEST'', ''QUARANTINED'', ''UNCLASSIFIED''))', table_name, table_name);
    END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS sources_data_origin_idx ON sources (data_origin, origin_owner);
CREATE INDEX IF NOT EXISTS evidence_versions_data_origin_idx ON evidence_versions (data_origin, origin_owner);
CREATE INDEX IF NOT EXISTS collection_runs_data_origin_idx ON collection_runs (data_origin, origin_owner);
CREATE INDEX IF NOT EXISTS github_project_inventory_data_origin_idx ON github_project_inventory (data_origin, origin_owner);

CREATE TABLE IF NOT EXISTS data_governance_audits (
    audit_id TEXT PRIMARY KEY,
    operation TEXT NOT NULL CHECK (operation IN ('BACKFILL', 'PREVIEW', 'CLEANUP', 'QUARANTINE', 'RETENTION')),
    status TEXT NOT NULL CHECK (status IN ('PLANNED', 'APPLIED', 'ABORTED')),
    selector JSONB NOT NULL,
    plan JSONB NOT NULL,
    input_fingerprint TEXT NOT NULL CHECK (length(trim(input_fingerprint)) = 64),
    policy_version TEXT NOT NULL CHECK (length(trim(policy_version)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS data_governance_audits_operation_idx ON data_governance_audits (operation, created_at DESC);

CREATE TABLE IF NOT EXISTS data_quarantine_records (
    quarantine_id TEXT PRIMARY KEY,
    table_name TEXT NOT NULL,
    row_key TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    reason_code TEXT NOT NULL,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS data_quarantine_records_open_idx ON data_quarantine_records (resolved_at, created_at DESC);
