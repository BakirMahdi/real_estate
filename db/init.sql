CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS properties (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    ad_id TEXT NOT NULL,
    property_type TEXT NOT NULL,
    listing_type TEXT NOT NULL DEFAULT 'sale',
    title TEXT NOT NULL,
    description TEXT,
    price DOUBLE PRECISION,
    area INTEGER,
    city TEXT,
    address TEXT,
    governorate TEXT,
    url TEXT NOT NULL,
    bedrooms INTEGER,
    garage BOOLEAN,
    furnished BOOLEAN,
    terrace BOOLEAN,
    pool BOOLEAN,
    subcategory TEXT,
    images TEXT[] DEFAULT '{}',
    archived BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_properties_city ON properties(city);
CREATE INDEX IF NOT EXISTS idx_properties_governorate ON properties(governorate);
CREATE INDEX IF NOT EXISTS idx_properties_type ON properties(property_type);
CREATE INDEX IF NOT EXISTS idx_properties_listing_type ON properties(listing_type);
CREATE INDEX IF NOT EXISTS idx_properties_price ON properties(price);
CREATE INDEX IF NOT EXISTS idx_properties_area ON properties(area);
