ALTER TABLE properties ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS ad_id TEXT;

UPDATE properties
SET source = 'tayara',
    ad_id = substring(url from '/item/([^/]+)/')
WHERE url LIKE '%tayara.tn/item/%'
  AND (source IS NULL OR ad_id IS NULL);

UPDATE properties
SET source = 'mubawab',
    ad_id = substring(url from '/(?:pa|a|p)/([0-9]+)')
WHERE url LIKE '%mubawab.tn%'
  AND (source IS NULL OR ad_id IS NULL);

ALTER TABLE properties DROP CONSTRAINT IF EXISTS properties_url_key;

ALTER TABLE properties ALTER COLUMN source SET NOT NULL;
ALTER TABLE properties ALTER COLUMN ad_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_properties_source_ad_id ON properties(source, ad_id);

ALTER TABLE properties ADD COLUMN IF NOT EXISTS listing_type TEXT NOT NULL DEFAULT 'sale';

UPDATE properties
SET listing_type = 'rent'
WHERE lower(coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(url, ''))
      ~ '(a[- ]?louer|location|louer|nuit[eé]e|كراء|للكراء)';

UPDATE properties
SET listing_type = 'sale'
WHERE listing_type = 'sale'
  AND lower(coalesce(title, '') || ' ' || coalesce(description, '') || ' ' || coalesce(url, ''))
      ~ '(a[- ]?vendre|vente|vendre|للبيع)';

CREATE INDEX IF NOT EXISTS idx_properties_listing_type ON properties(listing_type);

-- Merge houses into properties (single-table schema)
ALTER TABLE properties ADD COLUMN IF NOT EXISTS bedrooms INTEGER;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS bathrooms INTEGER;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS garage BOOLEAN;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS furnished BOOLEAN;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS terrace BOOLEAN;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS pool BOOLEAN;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS buildable BOOLEAN;
ALTER TABLE properties ADD COLUMN IF NOT EXISTS road_access BOOLEAN;

UPDATE properties p
SET
    bedrooms = h.bedrooms,
    bathrooms = h.bathrooms,
    garage = h.garage,
    furnished = h.furnished,
    terrace = h.terrace,
    pool = h.pool
FROM houses h
WHERE h.property_id = p.id
  AND p.property_type = 'house';

UPDATE properties
SET
    bedrooms = NULL,
    bathrooms = NULL,
    garage = NULL,
    furnished = NULL,
    terrace = NULL,
    pool = NULL
WHERE property_type = 'land';

UPDATE properties
SET
    buildable = NULL,
    road_access = NULL
WHERE property_type = 'house';

DROP TABLE IF EXISTS lands;
DROP TABLE IF EXISTS houses;
