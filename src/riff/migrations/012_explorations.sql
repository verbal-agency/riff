-- G11 bounded Explorations and experiment refinement history.

CREATE TABLE explorations (
    exploration_id TEXT PRIMARY KEY,
    riff_id TEXT NOT NULL UNIQUE REFERENCES riffs(riff_id),
    approval_decision_id TEXT NOT NULL REFERENCES riff_decisions(decision_id),
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'REFINING', 'SELECTED', 'ARCHIVED')),
    thesis TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    what_i_want_to_understand TEXT NOT NULL,
    capability_targets JSONB NOT NULL,
    technology_targets JSONB NOT NULL,
    open_questions JSONB NOT NULL,
    estimated_effort JSONB NOT NULL,
    evidence_of_competence JSONB NOT NULL,
    selected_experiment_id TEXT,
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE exploration_experiments (
    experiment_id TEXT PRIMARY KEY,
    exploration_id TEXT NOT NULL REFERENCES explorations(exploration_id),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    target_capability_id TEXT NOT NULL,
    technology_ids JSONB NOT NULL,
    learning_steps JSONB NOT NULL,
    effort_hours NUMERIC(5,2) NOT NULL CHECK (effort_hours >= 4 AND effort_hours <= 20),
    effort_assumptions JSONB NOT NULL,
    artifact_or_measurement TEXT NOT NULL,
    competence_evidence JSONB NOT NULL,
    selection_rules JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'REJECTED', 'SELECTED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE exploration_versions (
    version_id TEXT PRIMARY KEY,
    exploration_id TEXT NOT NULL REFERENCES explorations(exploration_id),
    version INTEGER NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (exploration_id, version)
);

CREATE TABLE exploration_events (
    event_id TEXT PRIMARY KEY,
    exploration_id TEXT NOT NULL REFERENCES explorations(exploration_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('CREATED', 'EXPERIMENT_REJECTED', 'REFINED', 'EXPERIMENT_SELECTED', 'ARCHIVED')),
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE explorations ADD CONSTRAINT explorations_selected_experiment_fk FOREIGN KEY (selected_experiment_id) REFERENCES exploration_experiments(experiment_id);

CREATE INDEX exploration_experiments_exploration_idx ON exploration_experiments (exploration_id, created_at);
CREATE INDEX exploration_events_exploration_idx ON exploration_events (exploration_id, created_at);
