-- G03 GitHub repository identity and normalized artifact metadata.

CREATE TABLE github_repositories (
    provider_repository_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    owner_login TEXT NOT NULL CHECK (length(trim(owner_login)) > 0),
    organization_login TEXT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    canonical_url TEXT NOT NULL CHECK (length(trim(canonical_url)) > 0),
    is_fork BOOLEAN NOT NULL DEFAULT FALSE,
    is_mirror BOOLEAN NOT NULL DEFAULT FALSE,
    stars INTEGER CHECK (stars IS NULL OR stars >= 0),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE github_repository_aliases (
    provider_repository_id TEXT NOT NULL REFERENCES github_repositories(provider_repository_id),
    owner_login TEXT NOT NULL,
    name TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (provider_repository_id, canonical_url)
);

CREATE TABLE github_artifacts (
    evidence_id TEXT PRIMARY KEY REFERENCES evidence_versions(evidence_id),
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    provider_artifact_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL CHECK (artifact_type IN (
        'REPOSITORY', 'RELEASE', 'README_CHANGE', 'ISSUE', 'DISCUSSION',
        'DEPENDENCY', 'ACTIVITY'
    )),
    provider_repository_id TEXT NOT NULL REFERENCES github_repositories(provider_repository_id),
    author_login TEXT,
    author_type TEXT,
    observed_at TIMESTAMPTZ NOT NULL,
    canonical_url TEXT NOT NULL,
    bounded BOOLEAN NOT NULL DEFAULT FALSE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX github_artifacts_repository_idx ON github_artifacts (provider_repository_id);
CREATE INDEX github_artifacts_source_type_idx ON github_artifacts (source_id, artifact_type);
CREATE INDEX github_artifacts_observed_at_idx ON github_artifacts (observed_at);
CREATE INDEX github_repositories_organization_idx ON github_repositories (organization_login);
