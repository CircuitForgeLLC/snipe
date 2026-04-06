-- Staging DB: persistent listing tracking across searches.
-- Adds temporal metadata to listings so we can detect stale/repriced/recurring items.

-- IF NOT EXISTS (SQLite 3.35+, Python 3.11 ships 3.39+) makes this safe to re-run
-- in any state: fresh install, partial-failure recovery, or already-applied.
ALTER TABLE listings ADD COLUMN IF NOT EXISTS first_seen_at       TEXT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS last_seen_at        TEXT;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS times_seen          INTEGER NOT NULL DEFAULT 1;
ALTER TABLE listings ADD COLUMN IF NOT EXISTS price_at_first_seen REAL;

-- Backfill existing rows so columns are non-null where we have data
UPDATE listings SET
    first_seen_at       = fetched_at,
    last_seen_at        = fetched_at,
    price_at_first_seen = price
WHERE first_seen_at IS NULL;

-- Price history: append-only snapshots; one row per (listing, price) change.
-- Duplicate prices are ignored (INSERT OR IGNORE) so only transitions are recorded.
CREATE TABLE IF NOT EXISTS listing_price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id  INTEGER NOT NULL REFERENCES listings(id),
    price       REAL NOT NULL,
    captured_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(listing_id, price)
);
