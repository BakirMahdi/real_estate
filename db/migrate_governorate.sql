-- Add governorate column to properties table (backfill via
-- `python -m scraper.backfill_governorate`).
ALTER TABLE properties ADD COLUMN IF NOT EXISTS governorate TEXT;
CREATE INDEX IF NOT EXISTS idx_properties_governorate ON properties(governorate);
