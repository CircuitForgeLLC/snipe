-- Make account_age_days nullable — scraper tier cannot fetch it without
-- following each seller's profile link, so NULL means "not yet fetched"
-- rather than "genuinely zero days old". This prevents false new_account
-- flags for all scraped listings.
--
-- SQLite doesn't support ALTER COLUMN, so we recreate the sellers table.

CREATE TABLE sellers_new (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    platform              TEXT NOT NULL,
    platform_seller_id    TEXT NOT NULL,
    username              TEXT NOT NULL,
    account_age_days      INTEGER,              -- NULL = not yet fetched
    feedback_count        INTEGER NOT NULL,
    feedback_ratio        REAL NOT NULL,
    category_history_json TEXT NOT NULL DEFAULT '{}',
    fetched_at            TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_seller_id)
);

INSERT INTO sellers_new SELECT * FROM sellers;
DROP TABLE sellers;
ALTER TABLE sellers_new RENAME TO sellers;
