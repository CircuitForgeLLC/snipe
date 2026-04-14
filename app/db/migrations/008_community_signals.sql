-- Community trust signals: user feedback on individual trust scores.
-- "This score looks right" (confirmed=1) / "This score is wrong" (confirmed=0).
-- Stored in shared_db so signals aggregate across all users.
CREATE TABLE IF NOT EXISTS community_signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id   TEXT NOT NULL,
    confirmed   INTEGER NOT NULL CHECK (confirmed IN (0, 1)),
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_community_signals_seller ON community_signals(seller_id);
