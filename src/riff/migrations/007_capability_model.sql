-- G06 reversible capability/technology normalization over immutable receipts.

CREATE TABLE capabilities (
    capability_id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    normalized_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RETIRED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE technologies (
    technology_id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    normalized_name TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL CHECK (length(trim(kind)) > 0),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RETIRED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE capability_concepts (
    concept_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL REFERENCES capabilities(capability_id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    UNIQUE (capability_id, name)
);

CREATE TABLE capability_patterns (
    pattern_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL REFERENCES capabilities(capability_id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    UNIQUE (capability_id, name)
);

CREATE TABLE capability_aliases (
    alias_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL REFERENCES capabilities(capability_id),
    alias_text TEXT NOT NULL CHECK (length(trim(alias_text)) > 0),
    normalized_alias TEXT NOT NULL UNIQUE
);

CREATE TABLE capability_mappings (
    mapping_id TEXT PRIMARY KEY,
    receipt_id TEXT NOT NULL REFERENCES evidence_receipts(receipt_id),
    candidate_text TEXT NOT NULL CHECK (length(trim(candidate_text)) > 0),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('CAPABILITY', 'TECHNOLOGY')),
    entity_id TEXT,
    normalizer_version TEXT NOT NULL CHECK (length(trim(normalizer_version)) > 0),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'ACCEPTED', 'REJECTED', 'SUPERSEDED')),
    rationale TEXT NOT NULL CHECK (length(trim(rationale)) > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX capability_mappings_identity_uq ON capability_mappings (
    receipt_id, entity_type, lower(candidate_text), normalizer_version, COALESCE(entity_id, '')
);

CREATE TABLE capability_relationships (
    relationship_id TEXT PRIMARY KEY,
    capability_id TEXT NOT NULL REFERENCES capabilities(capability_id),
    technology_id TEXT NOT NULL REFERENCES technologies(technology_id),
    relationship_type TEXT NOT NULL CHECK (relationship_type IN ('IMPLEMENTS', 'USED_WITH')),
    confidence NUMERIC(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RETIRED')),
    mapping_id TEXT REFERENCES capability_mappings(mapping_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (capability_id, technology_id, relationship_type)
);

CREATE TABLE normalization_decisions (
    decision_id TEXT PRIMARY KEY,
    mapping_id TEXT NOT NULL REFERENCES capability_mappings(mapping_id),
    action TEXT NOT NULL CHECK (action IN ('ACCEPT', 'REJECT', 'REMAP', 'SPLIT', 'UNDO')),
    actor TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    previous_entity_id TEXT,
    previous_status TEXT,
    new_entity_id TEXT,
    new_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX capability_mappings_receipt_idx ON capability_mappings (receipt_id, created_at);
CREATE INDEX capability_mappings_entity_idx ON capability_mappings (entity_type, entity_id, status);
CREATE INDEX capability_relationships_capability_idx ON capability_relationships (capability_id, status);
CREATE INDEX capability_relationships_technology_idx ON capability_relationships (technology_id, status);
CREATE INDEX normalization_decisions_mapping_idx ON normalization_decisions (mapping_id, created_at);
