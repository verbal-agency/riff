-- Preserve existing test and operator cleanup behavior for G41 audit events.

ALTER TABLE pipeline_run_events
    DROP CONSTRAINT IF EXISTS pipeline_run_events_run_id_fkey;

ALTER TABLE pipeline_run_events
    ADD CONSTRAINT pipeline_run_events_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id) ON DELETE CASCADE;
