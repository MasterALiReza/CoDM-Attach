-- Drop old tables if they exist
DROP TABLE IF EXISTS guide_photos;
DROP TABLE IF EXISTS guide_videos;

-- Create unified guide_media table
CREATE TABLE IF NOT EXISTS guide_media (
    id SERIAL PRIMARY KEY,
    guide_id INTEGER NOT NULL REFERENCES guides(id) ON DELETE CASCADE,
    media_type TEXT NOT NULL CHECK (media_type IN ('photo', 'video')),
    file_id TEXT NOT NULL,
    caption TEXT,
    order_index INTEGER DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Index for performance
CREATE INDEX IF NOT EXISTS idx_guide_media_guide ON guide_media (guide_id);
CREATE INDEX IF NOT EXISTS idx_guide_media_order ON guide_media (guide_id, order_index);
