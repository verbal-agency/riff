-- G13 durable daily-funnel run and stage state.

CREATE TABLE pipeline_runs (
    run_id TEXT PRIMARY KEY,
    run_date DATE NOT NULL,
    policy_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'SUCCEEDED', 'EMPTY', 'FAILED')),
    current_stage TEXT,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_date, policy_version)
);

CREATE TABLE pipeline_stages (
    stage_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
    stage_name TEXT NOT NULL CHECK (stage_name IN ('COLLECT', 'RECEIPT', 'CAPABILITY', 'PROFILE', 'SIGNAL', 'RIFF', 'PUBLISH')),
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'RUNNING', 'COMPLETE', 'FAILED')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    input_count INTEGER NOT NULL DEFAULT 0 CHECK (input_count >= 0),
    output_count INTEGER NOT NULL DEFAULT 0 CHECK (output_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    policy_version TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0 CHECK (duration_ms >= 0),
    model_calls INTEGER NOT NULL DEFAULT 0 CHECK (model_calls >= 0),
    token_count INTEGER NOT NULL DEFAULT 0 CHECK (token_count >= 0),
    cost_estimate NUMERIC(12,6) NOT NULL DEFAULT 0 CHECK (cost_estimate >= 0),
    error TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    UNIQUE (run_id, stage_name)
);

CREATE INDEX pipeline_runs_date_idx ON pipeline_runs (run_date, updated_at DESC);
CREATE INDEX pipeline_stages_run_idx ON pipeline_stages (run_id, stage_name);
