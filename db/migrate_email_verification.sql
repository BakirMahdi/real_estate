-- Email verification for local sign-up (Module: auth hardening).
-- Local accounts must confirm a one-time code emailed to them before they can
-- log in. Google accounts are exempt: Google already verifies the email.

ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_code TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_expires_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_attempts INTEGER NOT NULL DEFAULT 0;

-- Existing accounts predate verification; treat them as already verified so no
-- current user (including the manually-created admin and prior Google users)
-- gets locked out.
UPDATE users SET email_verified = TRUE WHERE email_verified = FALSE;
