-- G19 keeps source-level engineer attribution with the existing ingestion config.
-- The metadata is copied into retrieval JSONB; no new evidence table is needed.
ALTER TABLE ingestion_source_configs
    ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;
