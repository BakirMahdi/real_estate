-- Google sign-in: users authenticated via Google have no local password,
-- so password_hash must be nullable.
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;
