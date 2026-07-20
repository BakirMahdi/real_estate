-- Saved listings. Keyed on (source, ad_id) rather than properties.id so a
-- favorite survives re-versioning: a re-scrape that changes a listing's
-- fields inserts a new properties row with the same (source, ad_id) (see the
-- _LATEST_PROPERTIES comment in scraper/queries.py), and this way the
-- favorite still resolves to whichever row is current instead of pointing at
-- a superseded one.
CREATE TABLE IF NOT EXISTS favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    ad_id TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, source, ad_id)
);
CREATE INDEX IF NOT EXISTS idx_favorites_user_id ON favorites(user_id);
