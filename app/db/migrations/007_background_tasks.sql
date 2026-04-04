-- 007_background_tasks.sql
-- Shared background task queue used by the LLM/vision task scheduler.
-- Schema mirrors the circuitforge-core standard.
-- Also adds UNIQUE constraint on trust_scores(listing_id) so save_trust_scores()
-- can use ON CONFLICT upsert semantics.

CREATE TABLE IF NOT EXISTS background_tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type   TEXT    NOT NULL,
    job_id      INTEGER NOT NULL DEFAULT 0,
    status      TEXT    NOT NULL DEFAULT 'queued',
    params      TEXT,
    error       TEXT,
    stage       TEXT,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_bg_tasks_status_type
    ON background_tasks (status, task_type);

-- Enable ON CONFLICT upsert in save_trust_scores() — idempotent on existing DBs.
CREATE UNIQUE INDEX IF NOT EXISTS idx_trust_scores_listing
    ON trust_scores (listing_id);
