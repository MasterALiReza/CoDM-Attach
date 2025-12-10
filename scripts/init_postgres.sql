-- PostgreSQL initialization script for CODM Attachments Bot
-- Creates required extensions, tables, constraints, and indexes

-- ========== Extensions ==========
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ========== Weapon Domain ==========
CREATE TABLE IF NOT EXISTS weapon_categories (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS weapons (
  id SERIAL PRIMARY KEY,
  category_id INTEGER NOT NULL REFERENCES weapon_categories(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  UNIQUE (category_id, name)
);

CREATE TABLE IF NOT EXISTS attachments (
  id SERIAL PRIMARY KEY,
  weapon_id INTEGER NOT NULL REFERENCES weapons(id) ON DELETE CASCADE,
  mode TEXT NOT NULL CHECK (mode IN ('br','mp')),
  code TEXT NOT NULL,
  name TEXT NOT NULL,
  image_file_id TEXT,
  is_top BOOLEAN NOT NULL DEFAULT FALSE,
  is_season_top BOOLEAN NOT NULL DEFAULT FALSE,
  order_index INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP
);

ALTER TABLE attachments
  ADD CONSTRAINT uq_attachment UNIQUE (weapon_id, mode, code);

CREATE INDEX IF NOT EXISTS idx_attachments_weapon_mode ON attachments (weapon_id, mode);
CREATE INDEX IF NOT EXISTS idx_attachments_is_top ON attachments (weapon_id, mode) WHERE is_top = TRUE;
CREATE INDEX IF NOT EXISTS idx_attachments_code_trgm ON attachments USING gin (code gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_attachments_name_trgm ON attachments USING gin (name gin_trgm_ops);

-- Seed default categories
INSERT INTO weapon_categories (name) VALUES
('assault_rifle'),('smg'),('lmg'),('sniper'),('marksman'),('shotgun'),('pistol'),('launcher')
ON CONFLICT (name) DO NOTHING;

-- ========== Users ==========
CREATE TABLE IF NOT EXISTS users (
  user_id BIGINT PRIMARY KEY,
  username TEXT,
  first_name TEXT,
  last_name TEXT,
  language TEXT DEFAULT 'fa',
  last_seen TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ========== Required Channels ==========
CREATE TABLE IF NOT EXISTS required_channels (
  channel_id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  url TEXT NOT NULL,
  priority INTEGER NOT NULL DEFAULT 999,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_required_channels_priority ON required_channels (priority ASC);

-- ========== Blacklist ==========
CREATE TABLE IF NOT EXISTS blacklisted_words (
  word TEXT PRIMARY KEY,
  category TEXT NOT NULL DEFAULT 'general',
  severity INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ========== Search Analytics ==========
CREATE TABLE IF NOT EXISTS search_history (
  id SERIAL PRIMARY KEY,
  user_id BIGINT,
  query TEXT NOT NULL,
  results_count INTEGER NOT NULL DEFAULT 0,
  execution_time_ms REAL NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS popular_searches (
  query TEXT PRIMARY KEY,
  search_count INTEGER NOT NULL DEFAULT 0,
  last_searched TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Helpful indexes for analytics
-- Ensure column exists if table was created by older versions without created_at
ALTER TABLE search_history
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();
CREATE INDEX IF NOT EXISTS idx_search_history_created_at ON search_history (created_at);

-- ========== RBAC ==========
CREATE TABLE IF NOT EXISTS roles (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  display_name TEXT,
  description TEXT,
  icon TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_permissions (
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission TEXT NOT NULL,
  PRIMARY KEY (role_id, permission)
);

CREATE TABLE IF NOT EXISTS admins (
  user_id BIGINT PRIMARY KEY,
  display_name TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_roles (
  user_id BIGINT NOT NULL REFERENCES admins(user_id) ON DELETE CASCADE,
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, role_id)
);

-- ========== User Submission Stats ==========
CREATE TABLE IF NOT EXISTS user_submission_stats (
  user_id BIGINT PRIMARY KEY,
  is_banned BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at TIMESTAMP,
  total_submissions INTEGER NOT NULL DEFAULT 0,
  daily_submissions INTEGER NOT NULL DEFAULT 0,
  daily_reset_date DATE,
  violation_count INTEGER NOT NULL DEFAULT 0,
  strike_count REAL NOT NULL DEFAULT 0,
  last_submission_at TIMESTAMP,
  approved_count INTEGER NOT NULL DEFAULT 0,
  banned_reason TEXT,
  banned_at TIMESTAMP,
  banned_until TIMESTAMP
);

-- Backward-compatible migration for existing databases
ALTER TABLE user_submission_stats
  ADD COLUMN IF NOT EXISTS total_submissions INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS daily_submissions INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS daily_reset_date DATE,
  ADD COLUMN IF NOT EXISTS violation_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS strike_count REAL NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS last_submission_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS approved_count INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS banned_reason TEXT,
  ADD COLUMN IF NOT EXISTS banned_at TIMESTAMP,
  ADD COLUMN IF NOT EXISTS banned_until TIMESTAMP;

-- ========== Guides ==========
CREATE TABLE IF NOT EXISTS guides (
  id SERIAL PRIMARY KEY,
  key TEXT NOT NULL UNIQUE,
  mode TEXT NOT NULL CHECK (mode IN ('br','mp')),
  name TEXT,
  code TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guide_photos (
  id SERIAL PRIMARY KEY,
  guide_id INTEGER NOT NULL REFERENCES guides(id) ON DELETE CASCADE,
  file_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS guide_videos (
  id SERIAL PRIMARY KEY,
  guide_id INTEGER NOT NULL REFERENCES guides(id) ON DELETE CASCADE,
  file_id TEXT NOT NULL
);

-- ========== Settings ==========
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT,
  description TEXT,
  category TEXT,
  updated_by BIGINT,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ========== FAQ & Feedback & Tickets ==========
CREATE TABLE IF NOT EXISTS faqs (
  id SERIAL PRIMARY KEY,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  category TEXT,
  views INTEGER NOT NULL DEFAULT 0,
  helpful_count INTEGER NOT NULL DEFAULT 0,
  not_helpful_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
  id SERIAL PRIMARY KEY,
  user_id BIGINT,
  rating INTEGER NOT NULL,
  category TEXT,
  message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tickets (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  category TEXT,
  subject TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'open',
  priority TEXT NOT NULL DEFAULT 'medium',
  assigned_to BIGINT,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticket_replies (
  id SERIAL PRIMARY KEY,
  ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL,
  message TEXT NOT NULL,
  is_admin BOOLEAN NOT NULL DEFAULT FALSE,
  attachments TEXT[],
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ticket_attachments (
  id SERIAL PRIMARY KEY,
  ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  reply_id INTEGER REFERENCES ticket_replies(id) ON DELETE CASCADE,
  file_id TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ticket_attachments_ticket_id ON ticket_attachments (ticket_id);
CREATE INDEX IF NOT EXISTS ix_ticket_attachments_reply_id ON ticket_attachments (reply_id);

-- ========== User Attachments Core ==========
CREATE TABLE IF NOT EXISTS user_attachments (
  id SERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  weapon_id INTEGER REFERENCES weapons(id) ON DELETE SET NULL,
  mode TEXT NOT NULL CHECK (mode IN ('br','mp')),
  category TEXT,
  custom_weapon_name TEXT,
  attachment_name TEXT NOT NULL,
  image_file_id TEXT,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  submitted_at TIMESTAMP NOT NULL DEFAULT NOW(),
  approved_at TIMESTAMP,
  approved_by BIGINT,
  rejected_at TIMESTAMP,
  rejected_by BIGINT,
  rejection_reason TEXT,
  like_count INTEGER NOT NULL DEFAULT 0,
  report_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_user_attachments_status_submitted ON user_attachments (status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS ix_user_attachments_user ON user_attachments (user_id);

-- ========== User Attachment Engagement (votes, views, clicks) ==========
CREATE TABLE IF NOT EXISTS user_attachment_engagement (
  user_id BIGINT NOT NULL,
  attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
  rating SMALLINT,
  total_views INTEGER,
  total_clicks INTEGER,
  first_view_date TIMESTAMP,
  last_view_date TIMESTAMP,
  feedback TEXT,
  PRIMARY KEY (user_id, attachment_id)
);
CREATE INDEX IF NOT EXISTS ix_uae_attachment_id ON user_attachment_engagement (attachment_id);
CREATE INDEX IF NOT EXISTS ix_uae_attachment_id_rating ON user_attachment_engagement (attachment_id, rating);

-- ========== User Attachment Reports ==========
CREATE TABLE IF NOT EXISTS user_attachment_reports (
  id SERIAL PRIMARY KEY,
  attachment_id INTEGER NOT NULL REFERENCES user_attachments(id) ON DELETE CASCADE,
  user_id BIGINT,
  reason TEXT,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_uar_attachment_id ON user_attachment_reports (attachment_id);
CREATE INDEX IF NOT EXISTS ix_uar_status ON user_attachment_reports (status);

  -- New columns for modern schema (backward compatible)
  ALTER TABLE user_attachment_reports
    ADD COLUMN IF NOT EXISTS reporter_id BIGINT,
    ADD COLUMN IF NOT EXISTS reported_at TIMESTAMP NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS resolved_by BIGINT,
    ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP;

  -- Legacy columns for backward compatibility (needed by some indexes and fallbacks)
  ALTER TABLE user_attachment_reports
    ADD COLUMN IF NOT EXISTS user_id BIGINT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT NOW();

-- Unique constraints to prevent multiple reports by same user on the same attachment
-- Apply both (new and legacy) to keep compatibility
CREATE UNIQUE INDEX IF NOT EXISTS ux_uar_att_reporter
  ON user_attachment_reports (attachment_id, reporter_id)
  WHERE reporter_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ux_uar_att_user
  ON user_attachment_reports (attachment_id, user_id)
  WHERE user_id IS NOT NULL;

-- Daily count helper indexes
CREATE INDEX IF NOT EXISTS ix_uar_reporter_day
  ON user_attachment_reports (reporter_id, reported_at)
  WHERE reporter_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_uar_user_day
  ON user_attachment_reports (user_id, created_at)
  WHERE user_id IS NOT NULL;

-- ========== Suggested Attachments ==========
CREATE TABLE IF NOT EXISTS suggested_attachments (
  attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
  mode TEXT NOT NULL CHECK (mode IN ('br','mp')),
  priority INTEGER NOT NULL DEFAULT 999,
  reason TEXT,
  added_by BIGINT,
  added_at TIMESTAMP NOT NULL DEFAULT NOW()
);
-- Unique index used by ON CONFLICT in code
CREATE UNIQUE INDEX IF NOT EXISTS ux_suggested_attachment_mode ON suggested_attachments (attachment_id, mode);
CREATE INDEX IF NOT EXISTS ix_suggested_mode ON suggested_attachments (mode);

-- ========== UA Settings ==========
CREATE TABLE IF NOT EXISTS user_attachment_settings (
  setting_key TEXT PRIMARY KEY,
  setting_value TEXT,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_by BIGINT
);

-- ========== UA Cache Tables ==========
CREATE TABLE IF NOT EXISTS ua_stats_cache (
  id INTEGER PRIMARY KEY,
  total_attachments INTEGER,
  pending_count INTEGER,
  approved_count INTEGER,
  rejected_count INTEGER,
  total_users INTEGER,
  active_users INTEGER,
  banned_users INTEGER,
  br_count INTEGER,
  mp_count INTEGER,
  total_likes INTEGER,
  total_reports INTEGER,
  pending_reports INTEGER,
  last_week_submissions INTEGER,
  last_week_approvals INTEGER,
  updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ua_top_weapons_cache (
  weapon_name TEXT NOT NULL,
  attachment_count INTEGER NOT NULL,
  mode TEXT,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ua_top_weapons_count ON ua_top_weapons_cache (attachment_count DESC);

CREATE TABLE IF NOT EXISTS ua_top_users_cache (
  user_id BIGINT NOT NULL,
  username TEXT,
  approved_count INTEGER NOT NULL,
  total_likes INTEGER NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_ua_top_users_count ON ua_top_users_cache (approved_count DESC);

-- ========== Data Health Reporting ==========
CREATE TABLE IF NOT EXISTS data_health_checks (
  id SERIAL PRIMARY KEY,
  check_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  category TEXT,
  issue_count INTEGER NOT NULL DEFAULT 0,
  details JSONB,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS data_quality_metrics (
  id SERIAL PRIMARY KEY,
  total_weapons INTEGER NOT NULL DEFAULT 0,
  total_attachments INTEGER NOT NULL DEFAULT 0,
  weapons_with_attachments INTEGER NOT NULL DEFAULT 0,
  weapons_without_attachments INTEGER NOT NULL DEFAULT 0,
  attachments_with_images INTEGER NOT NULL DEFAULT 0,
  attachments_without_images INTEGER NOT NULL DEFAULT 0,
  health_score REAL NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
