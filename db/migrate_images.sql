ALTER TABLE properties ADD COLUMN IF NOT EXISTS images TEXT[] DEFAULT '{}';
ALTER TABLE properties ADD COLUMN IF NOT EXISTS subcategory TEXT;

-- Backfill subcategory based on property_type or title keywords
UPDATE properties
SET subcategory = 'land'
WHERE subcategory IS NULL AND property_type = 'land';

UPDATE properties
SET subcategory = 'apartment'
WHERE subcategory IS NULL AND property_type = 'house' AND (
    lower(title || ' ' || description) ~ '(appart|s\s*\+\s*\d+|duplex|triplex)'
);

UPDATE properties
SET subcategory = 'office'
WHERE subcategory IS NULL AND property_type = 'house' AND (
    lower(title || ' ' || description) ~ '(bureau|commerce|local|magasin|depot|dépôt)'
);

UPDATE properties
SET subcategory = 'studio'
WHERE subcategory IS NULL AND property_type = 'house' AND (
    lower(title || ' ' || description) ~ '(studio|chambre|coloc)'
);

UPDATE properties
SET subcategory = 'house'
WHERE subcategory IS NULL AND property_type = 'house' AND (
    lower(title || ' ' || description) ~ '(maison|villa|dar|riad)'
);

UPDATE properties
SET subcategory = 'house'
WHERE subcategory IS NULL AND property_type = 'house';
