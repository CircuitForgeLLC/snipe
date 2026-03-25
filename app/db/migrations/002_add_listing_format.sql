-- Add auction metadata to listings (v0.1.1)
ALTER TABLE listings ADD COLUMN buying_format TEXT NOT NULL DEFAULT 'fixed_price';
ALTER TABLE listings ADD COLUMN ends_at TEXT;
