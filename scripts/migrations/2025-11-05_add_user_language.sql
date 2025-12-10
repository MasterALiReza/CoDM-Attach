-- Migration: Add language column to users table for i18n (fa/en)
-- Date: 2025-11-05

ALTER TABLE users 
    ADD COLUMN IF NOT EXISTS language TEXT CHECK (language IN ('fa', 'en'));

UPDATE users 
SET language = 'fa' 
WHERE language IS NULL;

CREATE INDEX IF NOT EXISTS idx_users_language ON users(language);

-- End of migration
