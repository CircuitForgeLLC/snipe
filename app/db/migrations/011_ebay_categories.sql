-- app/db/migrations/011_ebay_categories.sql
-- eBay category leaf node cache. Refreshed weekly via EbayCategoryCache.refresh().
-- Seeded with a small bootstrap table when no eBay API credentials are configured.
-- MIT License

CREATE TABLE IF NOT EXISTS ebay_categories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id  TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    full_path    TEXT NOT NULL,   -- "Consumer Electronics > ... > Leaf Name"
    is_leaf      INTEGER NOT NULL DEFAULT 1,  -- SQLite stores bool as int
    refreshed_at TEXT NOT NULL    -- ISO8601 timestamp
);

CREATE INDEX IF NOT EXISTS idx_ebay_cat_name
    ON ebay_categories (name);
