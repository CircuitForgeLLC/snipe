-- Migration 015: cross-user monitor registry for the background polling loop
--
-- In cloud mode this table lives in shared.db — the polling loop queries it
-- to find all due monitors without scanning per-user DB files.
-- In local mode it lives in the single local DB (same result, one user).
--
-- user_db_path references the per-user snipe user.db so the poller knows
-- which DB to open for the full SavedSearch config and to write alerts.

CREATE TABLE IF NOT EXISTS active_monitors (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_db_path      TEXT    NOT NULL,
    saved_search_id   INTEGER NOT NULL,
    poll_interval_min INTEGER NOT NULL DEFAULT 60,
    last_checked_at   TEXT,
    UNIQUE(user_db_path, saved_search_id)
);

CREATE INDEX IF NOT EXISTS idx_active_monitors_due
    ON active_monitors(last_checked_at);
