-- G30 repair metadata gaps and make stale collection reconciliation auditable.
ALTER TABLE collection_runs ADD COLUMN IF NOT EXISTS completion_reason TEXT;

UPDATE evidence_receipts AS r
SET source_metadata = r.source_metadata || jsonb_strip_nulls(jsonb_build_object(
    'evidence_id', COALESCE(r.source_metadata->>'evidence_id', r.evidence_id),
    'source_id', COALESCE(r.source_metadata->>'source_id', s.source_id),
    'source_type', COALESCE(r.source_metadata->>'source_type', s.source_type),
    'source_name', COALESCE(r.source_metadata->>'source_name', s.name),
    'canonical_root', COALESCE(r.source_metadata->>'canonical_root', s.canonical_root),
    'person_name', COALESCE(r.source_metadata->>'person_name', c.metadata->>'person_name'),
    'organization_at_publication', COALESCE(r.source_metadata->>'organization_at_publication', c.metadata->>'organization_at_publication'),
    'correlation_group', COALESCE(r.source_metadata->>'correlation_group', c.metadata->>'correlation_group'),
    'source_root', COALESCE(r.source_metadata->>'source_root', c.metadata->>'source_root')
))
FROM evidence_versions e
JOIN source_items si ON si.source_item_id = e.source_item_id
JOIN sources s ON s.source_id = si.source_id
LEFT JOIN ingestion_source_configs c ON c.source_id = s.source_id
WHERE r.evidence_id = e.evidence_id;
