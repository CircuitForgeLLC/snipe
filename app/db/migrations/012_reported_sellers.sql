CREATE TABLE IF NOT EXISTS reported_sellers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform            TEXT NOT NULL,
    platform_seller_id  TEXT NOT NULL,
    username            TEXT,
    reported_at         TEXT DEFAULT CURRENT_TIMESTAMP,
    reported_by         TEXT NOT NULL DEFAULT 'user',  -- user | bulk_action
    UNIQUE(platform, platform_seller_id)
);

CREATE INDEX IF NOT EXISTS idx_reported_sellers_lookup
    ON reported_sellers(platform, platform_seller_id);
