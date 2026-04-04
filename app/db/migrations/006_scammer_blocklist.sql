CREATE TABLE IF NOT EXISTS scammer_blocklist (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    platform            TEXT NOT NULL,
    platform_seller_id  TEXT NOT NULL,
    username            TEXT NOT NULL,
    reason              TEXT,
    source              TEXT NOT NULL DEFAULT 'manual',  -- manual | csv_import | community
    created_at          TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_seller_id)
);

CREATE INDEX IF NOT EXISTS idx_scammer_blocklist_lookup
    ON scammer_blocklist(platform, platform_seller_id);
