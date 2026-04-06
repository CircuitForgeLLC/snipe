-- Add per-listing category name, extracted from eBay API response.
-- Used to derive seller category_history_json without _ssn scraping.
ALTER TABLE listings ADD COLUMN IF NOT EXISTS category_name TEXT;
