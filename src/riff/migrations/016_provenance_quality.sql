-- G29 stores calibrated provenance separately from the generated candidate
-- score.  The JSON summary keeps the evidence snapshot and unknowns auditable.
ALTER TABLE riffs ADD COLUMN IF NOT EXISTS candidate_score NUMERIC(5,4);
ALTER TABLE riffs ADD COLUMN IF NOT EXISTS evidence_quality NUMERIC(5,4);
ALTER TABLE riffs ADD COLUMN IF NOT EXISTS epistemic_confidence NUMERIC(5,4);
ALTER TABLE riffs ADD COLUMN IF NOT EXISTS confidence_policy_version TEXT;
ALTER TABLE riffs ADD COLUMN IF NOT EXISTS provenance_summary JSONB;

UPDATE riffs
SET candidate_score = COALESCE(candidate_score, confidence),
    evidence_quality = COALESCE(evidence_quality, confidence),
    epistemic_confidence = COALESCE(epistemic_confidence, confidence),
    confidence_policy_version = COALESCE(confidence_policy_version, 'legacy-un-calibrated'),
    provenance_summary = COALESCE(provenance_summary, '{}'::jsonb);

ALTER TABLE riffs ALTER COLUMN candidate_score SET DEFAULT 0;
ALTER TABLE riffs ALTER COLUMN evidence_quality SET DEFAULT 0;
ALTER TABLE riffs ALTER COLUMN epistemic_confidence SET DEFAULT 0;
ALTER TABLE riffs ALTER COLUMN confidence_policy_version SET DEFAULT 'provenance-policy-v1';
ALTER TABLE riffs ALTER COLUMN provenance_summary SET DEFAULT '{}'::jsonb;
