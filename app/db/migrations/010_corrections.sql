-- LLM output corrections for SFT training pipeline (cf-core make_corrections_router).
-- Stores thumbs-up/down feedback and explicit corrections on LLM-generated content.
-- Used once #29 (LLM query builder) ships; table is safe to pre-create now.

CREATE TABLE IF NOT EXISTS corrections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id          TEXT    NOT NULL DEFAULT '',
    product          TEXT    NOT NULL,
    correction_type  TEXT    NOT NULL,
    input_text       TEXT    NOT NULL,
    original_output  TEXT    NOT NULL,
    corrected_output TEXT    NOT NULL DEFAULT '',
    rating           TEXT    NOT NULL DEFAULT 'down',
    context          TEXT    NOT NULL DEFAULT '{}',
    opted_in         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_corrections_product
    ON corrections (product);

CREATE INDEX IF NOT EXISTS idx_corrections_opted_in
    ON corrections (opted_in);
