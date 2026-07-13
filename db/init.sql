CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    -- The login identity is the user's email (Google accounts are keyed by it
    -- too). Column kept named `username` for backward compatibility.
    username TEXT UNIQUE NOT NULL,
    -- Nullable: Google-authenticated users have no local password.
    password_hash TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    -- Email ownership confirmed: TRUE for Google accounts and for local
    -- accounts that entered the emailed verification code.
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    verification_code TEXT,
    verification_expires_at TIMESTAMPTZ,
    verification_attempts INTEGER NOT NULL DEFAULT 0,
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
    bathrooms INTEGER,
    garage BOOLEAN,
    furnished BOOLEAN,
    terrace BOOLEAN,
    pool BOOLEAN,
    -- Land-only, mirroring bedrooms/garage/etc. being house-only: never
    -- populated by the current scrapers/insert.py (unreferenced elsewhere in
    -- the codebase), kept only so a fresh clone's schema matches what
    -- migrate_ad_id.sql already added to any pre-existing database.
    buildable BOOLEAN,
    road_access BOOLEAN,
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
-- Not UNIQUE: the app intentionally inserts a new row with the same
-- (source, ad_id) when a listing's fields change (versioning, see
-- scraper/insert.py) without archiving the old row first. This index exists
-- to speed up the DISTINCT ON (source, ad_id) ... ORDER BY source, ad_id, id
-- lookup used by the main search query (see scraper/queries.py).
CREATE INDEX IF NOT EXISTS idx_properties_source_ad_id ON properties(source, ad_id, id DESC);

-- Module 5: conversational agent. One ongoing conversation thread per user
-- (messages appended as a JSON array), resumed whenever they reconnect.
CREATE TABLE IF NOT EXISTS agent_conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    messages JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
