-- Migration 013: eBay user OAuth tokens
--
-- Stores per-user eBay Authorization Code tokens so the app can call
-- Trading API GetUser for instant account_age_days + category feedback
-- without Playwright scraping.
--
-- Stored in the per-user DB (user.db), never the shared DB.
-- access_token is short-lived (2h); refresh_token is valid 18 months.
-- The API layer refreshes access_token automatically before expiry.

CREATE TABLE IF NOT EXISTS ebay_user_tokens (
    id               INTEGER PRIMARY KEY,
    -- Single row per user DB — upsert on reconnect
    access_token     TEXT    NOT NULL,
    refresh_token    TEXT    NOT NULL,
    expires_at       REAL    NOT NULL,   -- epoch seconds; access token expiry
    scopes           TEXT    NOT NULL DEFAULT '',
    connected_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    last_refreshed   TEXT
);
