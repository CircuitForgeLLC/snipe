-- Migration 014: background monitor settings on saved_searches + watch_alerts table

ALTER TABLE saved_searches ADD COLUMN monitor_enabled   INTEGER NOT NULL DEFAULT 0;
ALTER TABLE saved_searches ADD COLUMN poll_interval_min INTEGER NOT NULL DEFAULT 60;
ALTER TABLE saved_searches ADD COLUMN min_trust_score   INTEGER NOT NULL DEFAULT 60;
ALTER TABLE saved_searches ADD COLUMN last_checked_at   TEXT;

CREATE TABLE IF NOT EXISTS watch_alerts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    saved_search_id     INTEGER NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,
    platform_listing_id TEXT    NOT NULL,
    title               TEXT    NOT NULL,
    price               REAL    NOT NULL,
    currency            TEXT    NOT NULL DEFAULT 'USD',
    trust_score         INTEGER NOT NULL,
    url                 TEXT,
    first_alerted_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dismissed_at        TEXT,
    UNIQUE(saved_search_id, platform_listing_id)
);

CREATE INDEX IF NOT EXISTS idx_watch_alerts_undismissed
    ON watch_alerts(saved_search_id)
    WHERE dismissed_at IS NULL;
