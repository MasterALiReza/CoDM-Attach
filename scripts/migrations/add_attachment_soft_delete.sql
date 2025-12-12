-- Add 'deleted' to status check constraint
ALTER TABLE user_attachments DROP CONSTRAINT IF EXISTS user_attachments_status_check;
ALTER TABLE user_attachments ADD CONSTRAINT user_attachments_status_check 
    CHECK (status IN ('pending', 'approved', 'rejected', 'deleted', 'irrelevant'));

-- Add deleted tracking columns
ALTER TABLE user_attachments ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
ALTER TABLE user_attachments ADD COLUMN IF NOT EXISTS deleted_by BIGINT REFERENCES users(user_id);

-- Add deleted_count to stats
ALTER TABLE user_submission_stats ADD COLUMN IF NOT EXISTS deleted_count INTEGER NOT NULL DEFAULT 0;

-- Update stats cache table
ALTER TABLE ua_stats_cache ADD COLUMN IF NOT EXISTS deleted_count INTEGER DEFAULT 0;
