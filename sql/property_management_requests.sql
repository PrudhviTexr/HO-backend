-- Optional Supabase table for property management intake (JSON file fallback works without this)
CREATE TABLE IF NOT EXISTS property_management_requests (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  status TEXT NOT NULL DEFAULT 'new',
  name TEXT NOT NULL,
  email TEXT NOT NULL,
  phone TEXT NOT NULL,
  property_type TEXT NOT NULL,
  listing_type TEXT,
  state TEXT,
  district TEXT,
  city TEXT,
  address TEXT,
  pincode TEXT,
  bedrooms TEXT,
  bathrooms TEXT,
  area_sqft TEXT,
  furnishing TEXT,
  expected_rent TEXT,
  expected_price TEXT,
  services_needed JSONB,
  preferred_contact_time TEXT,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pm_requests_created ON property_management_requests (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pm_requests_status ON property_management_requests (status);
