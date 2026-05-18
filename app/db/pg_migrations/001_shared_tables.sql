-- Snipe shared tables: sellers, market_comps, reported_sellers
-- Replaces the equivalent tables in shared.db (SQLite).
-- Per-user tables (listings, trust_scores, saved_searches) remain in SQLite.

CREATE TABLE IF NOT EXISTS sellers (
    id                    BIGSERIAL PRIMARY KEY,
    platform              TEXT NOT NULL,
    platform_seller_id    TEXT NOT NULL,
    username              TEXT NOT NULL,
    account_age_days      INTEGER,
    feedback_count        INTEGER NOT NULL DEFAULT 0,
    feedback_ratio        DOUBLE PRECISION NOT NULL DEFAULT 0,
    category_history_json TEXT NOT NULL DEFAULT '{}',
    fetched_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, platform_seller_id)
);

CREATE TABLE IF NOT EXISTS market_comps (
    id           BIGSERIAL PRIMARY KEY,
    platform     TEXT NOT NULL,
    query_hash   TEXT NOT NULL,
    median_price DOUBLE PRECISION NOT NULL,
    sample_count INTEGER NOT NULL,
    fetched_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at   TIMESTAMPTZ NOT NULL,
    UNIQUE (platform, query_hash)
);

CREATE TABLE IF NOT EXISTS reported_sellers (
    id                  BIGSERIAL PRIMARY KEY,
    platform            TEXT NOT NULL,
    platform_seller_id  TEXT NOT NULL,
    username            TEXT,
    reported_by         TEXT NOT NULL DEFAULT 'user',
    reported_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (platform, platform_seller_id)
);

