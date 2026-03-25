CREATE TABLE IF NOT EXISTS sellers (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    platform              TEXT NOT NULL,
    platform_seller_id    TEXT NOT NULL,
    username              TEXT NOT NULL,
    account_age_days      INTEGER NOT NULL,
    feedback_count        INTEGER NOT NULL,
    feedback_ratio        REAL NOT NULL,
    category_history_json TEXT NOT NULL DEFAULT '{}',
    fetched_at            TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_seller_id)
);

CREATE TABLE IF NOT EXISTS listings (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    platform             TEXT NOT NULL,
    platform_listing_id  TEXT NOT NULL,
    title                TEXT NOT NULL,
    price                REAL NOT NULL,
    currency             TEXT NOT NULL DEFAULT 'USD',
    condition            TEXT,
    seller_platform_id   TEXT,
    url                  TEXT,
    photo_urls           TEXT NOT NULL DEFAULT '[]',
    listing_age_days     INTEGER DEFAULT 0,
    fetched_at           TEXT DEFAULT CURRENT_TIMESTAMP,
    trust_score_id       INTEGER REFERENCES trust_scores(id),
    UNIQUE(platform, platform_listing_id)
);

CREATE TABLE IF NOT EXISTS trust_scores (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id             INTEGER NOT NULL REFERENCES listings(id),
    composite_score        INTEGER NOT NULL,
    account_age_score      INTEGER NOT NULL DEFAULT 0,
    feedback_count_score   INTEGER NOT NULL DEFAULT 0,
    feedback_ratio_score   INTEGER NOT NULL DEFAULT 0,
    price_vs_market_score  INTEGER NOT NULL DEFAULT 0,
    category_history_score INTEGER NOT NULL DEFAULT 0,
    photo_hash_duplicate   INTEGER NOT NULL DEFAULT 0,
    photo_analysis_json    TEXT,
    red_flags_json         TEXT NOT NULL DEFAULT '[]',
    score_is_partial       INTEGER NOT NULL DEFAULT 0,
    scored_at              TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_comps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    platform     TEXT NOT NULL,
    query_hash   TEXT NOT NULL,
    median_price REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    fetched_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at   TEXT NOT NULL,
    UNIQUE(platform, query_hash)
);

CREATE TABLE IF NOT EXISTS saved_searches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    query        TEXT NOT NULL,
    platform     TEXT NOT NULL DEFAULT 'ebay',
    filters_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    last_run_at  TEXT
);

-- PhotoHash: perceptual hash store for cross-search dedup (v0.2+). Schema present in v0.1.
CREATE TABLE IF NOT EXISTS photo_hashes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id   INTEGER NOT NULL REFERENCES listings(id),
    photo_url    TEXT NOT NULL,
    phash        TEXT NOT NULL,
    first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(listing_id, photo_url)
);
