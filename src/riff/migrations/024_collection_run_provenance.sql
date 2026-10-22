-- G48 collection-run provenance and auditable resolution reasons.
ALTER TABLE collection_runs ADD COLUMN IF NOT EXISTS origin_reason TEXT;
