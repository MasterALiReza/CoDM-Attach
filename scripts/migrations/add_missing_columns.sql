-- Migration: Add missing columns to user attachment tables
-- Date: 2025-12-12
-- Purpose: Fix "column does not exist" errors in ua_cache and statistics handlers

-- Add is_banned column to user_submission_stats if not exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_submission_stats' 
        AND column_name = 'is_banned'
    ) THEN
        ALTER TABLE user_submission_stats
        ADD COLUMN is_banned BOOLEAN NOT NULL DEFAULT FALSE;
        
        RAISE NOTICE 'Added is_banned column to user_submission_stats';
    ELSE
        RAISE NOTICE 'Column is_banned already exists in user_submission_stats';
    END IF;
END $$;

-- Add view_count column to user_attachments if not exists  
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_attachments' 
        AND column_name = 'view_count'
    ) THEN
        ALTER TABLE user_attachments
        ADD COLUMN view_count INTEGER NOT NULL DEFAULT 0;
        
        RAISE NOTICE 'Added view_count column to user_attachments';
    ELSE
        RAISE NOTICE 'Column view_count already exists in user_attachments';
    END IF;
END $$;

-- Create index for better performance on banned users query
CREATE INDEX IF NOT EXISTS idx_user_submission_stats_banned 
ON user_submission_stats (is_banned) 
WHERE is_banned = TRUE;

-- Update existing records (set defaults for any NULL values from before migration)
UPDATE user_submission_stats SET is_banned = FALSE WHERE is_banned IS NULL;
UPDATE user_attachments SET view_count = 0 WHERE view_count IS NULL;

-- Display success message
DO $$
BEGIN
    RAISE NOTICE '✅ Migration completed successfully!';
    RAISE NOTICE 'Summary:';
    RAISE NOTICE '  - is_banned column added/verified in user_submission_stats';
    RAISE NOTICE '  - view_count column added/verified in user_attachments';
    RAISE NOTICE '  - Performance index created on is_banned column';
END $$;
