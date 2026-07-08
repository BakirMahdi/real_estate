-- Add archived column to properties table
ALTER TABLE properties ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE;

-- Add role column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'user';

-- Update existing admin user to have admin role
UPDATE users SET role = 'admin' WHERE username = 'admin';
