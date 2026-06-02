-- Run in Supabase SQL editor for featured property ordering on the home page
ALTER TABLE properties ADD COLUMN IF NOT EXISTS featured_order INTEGER;

CREATE INDEX IF NOT EXISTS idx_properties_featured_order ON properties (featured_order)
WHERE featured = true;
