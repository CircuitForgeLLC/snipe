-- Per-user preferences stored as a single JSON blob.
-- Lives in user_db (each user has their own DB file) — never in shared.db.
-- Single-row enforced by PRIMARY KEY CHECK (id = 1): acts as a singleton table.
-- Path reads/writes use cf-core preferences.paths (get_path / set_path).
CREATE TABLE IF NOT EXISTS user_preferences (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    prefs_json  TEXT    NOT NULL DEFAULT '{}',
    updated_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
