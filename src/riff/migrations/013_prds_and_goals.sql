-- G12 learning PRDs, explicit PRD approvals, and agent-ready goals.

CREATE TABLE prd_approvals (
    approval_id TEXT PRIMARY KEY,
    exploration_id TEXT NOT NULL REFERENCES explorations(exploration_id),
    actor TEXT NOT NULL,
    actor_kind TEXT NOT NULL CHECK (actor_kind = 'USER'),
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    exploration_id TEXT NOT NULL UNIQUE REFERENCES explorations(exploration_id),
    approval_id TEXT NOT NULL REFERENCES prd_approvals(approval_id),
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'READY', 'ARCHIVED')),
    version INTEGER NOT NULL CHECK (version > 0),
    useful_hours NUMERIC(5,2) NOT NULL CHECK (useful_hours >= 4 AND useful_hours <= 20),
    prd JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE project_goals (
    goal_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    title TEXT NOT NULL,
    outcome TEXT NOT NULL,
    inputs JSONB NOT NULL,
    deliverable TEXT NOT NULL,
    dependencies JSONB NOT NULL,
    non_goals JSONB NOT NULL,
    acceptance_criteria JSONB NOT NULL,
    verification_evidence JSONB NOT NULL,
    UNIQUE (project_id, ordinal)
);

CREATE TABLE project_versions (
    version_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id),
    version INTEGER NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (project_id, version)
);

CREATE INDEX prd_approvals_exploration_idx ON prd_approvals (exploration_id, created_at);
CREATE INDEX project_goals_project_idx ON project_goals (project_id, ordinal);
