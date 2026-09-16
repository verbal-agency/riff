-- G33 scoped, user-authorized GitHub account observations and repository selections.

ALTER TABLE github_project_inventory
    ADD COLUMN IF NOT EXISTS account_observation_id TEXT,
    ADD COLUMN IF NOT EXISTS account_selection_id TEXT;

CREATE TABLE github_account_observations (
    observation_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL CHECK (provider = 'GITHUB'),
    provider_account_id TEXT NOT NULL,
    username TEXT NOT NULL CHECK (length(trim(username)) > 0),
    scope TEXT NOT NULL CHECK (scope IN ('PUBLIC_METADATA', 'PUBLIC_METADATA_AND_ACTIVITY')),
    scope_version INTEGER NOT NULL CHECK (scope_version >= 1),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVOKED', 'SCOPE_NARROWED')),
    consented_at TIMESTAMPTZ NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    last_success_at TIMESTAMPTZ,
    input_fingerprint TEXT NOT NULL CHECK (length(trim(input_fingerprint)) = 64),
    omitted_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, provider_account_id, scope_version)
);

CREATE INDEX github_account_observations_current_idx
    ON github_account_observations (provider, provider_account_id, scope_version DESC);

CREATE TABLE github_account_observation_repositories (
    observation_id TEXT NOT NULL REFERENCES github_account_observations(observation_id),
    provider_repository_id TEXT NOT NULL,
    full_name TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
    canonical_url TEXT NOT NULL CHECK (length(trim(canonical_url)) > 0),
    visibility TEXT NOT NULL CHECK (visibility IN ('PUBLIC', 'PRIVATE', 'UNKNOWN')),
    availability TEXT NOT NULL CHECK (availability IN ('AVAILABLE', 'OMITTED', 'UNKNOWN')),
    is_fork BOOLEAN NOT NULL DEFAULT FALSE,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    omitted_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    uncertainty JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (observation_id, provider_repository_id)
);

CREATE INDEX github_account_observation_repositories_name_idx
    ON github_account_observation_repositories (observation_id, full_name);

CREATE TABLE github_account_observation_events (
    event_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES github_account_observations(observation_id),
    event_type TEXT NOT NULL CHECK (event_type IN ('OBSERVED', 'REVOKED', 'SCOPE_NARROWED')),
    previous_status TEXT,
    new_status TEXT NOT NULL CHECK (new_status IN ('ACTIVE', 'REVOKED', 'SCOPE_NARROWED')),
    previous_scope TEXT,
    new_scope TEXT NOT NULL CHECK (new_scope IN ('PUBLIC_METADATA', 'PUBLIC_METADATA_AND_ACTIVITY')),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX github_account_observation_events_idx
    ON github_account_observation_events (observation_id, created_at);

CREATE TABLE github_account_repository_selections (
    selection_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES github_account_observations(observation_id),
    provider_repository_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'ONBOARDED', 'DECLINED')),
    project_id TEXT REFERENCES github_project_inventory(project_id),
    selected_by TEXT NOT NULL CHECK (length(trim(selected_by)) > 0),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (observation_id, provider_repository_id)
);

CREATE INDEX github_account_repository_selections_status_idx
    ON github_account_repository_selections (observation_id, status);

ALTER TABLE github_project_inventory
    ADD CONSTRAINT github_project_inventory_account_observation_fk
        FOREIGN KEY (account_observation_id) REFERENCES github_account_observations(observation_id),
    ADD CONSTRAINT github_project_inventory_account_selection_fk
        FOREIGN KEY (account_selection_id) REFERENCES github_account_repository_selections(selection_id);

CREATE INDEX github_project_inventory_account_observation_idx
    ON github_project_inventory (account_observation_id);
