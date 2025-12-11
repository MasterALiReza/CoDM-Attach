-- ============================================================================
-- CODM Attachments Bot - Complete Database Setup Script
-- ============================================================================
-- Database Name: codm_attachments_db
-- User: codm_bot_user
-- Version: 2.0 - Clean & Organized
-- Created: 2025-11-26
-- ============================================================================

-- STEP 1: Create User (if not exists)
-- Note: Run this as postgres superuser
-- Password is set by deploy.sh script dynamically
-- DO NOT hardcode password here for security

-- Grant necessary privileges (user created by deploy.sh)
-- ALTER ROLE codm_bot_user WITH CREATEDB;

-- ============================================================================
-- STEP 2: Extensions (must be in the database)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ============================================================================
-- STEP 3: Core Weapon & Attachment Tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS weapon_categories (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT,
    icon TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weapons (
    id SERIAL PRIMARY KEY,
    category_id INTEGER NOT NULL REFERENCES weapon_categories(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    display_name TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    UNIQUE (category_id, name)
);

CREATE TABLE IF NOT EXISTS attachments (
    id SERIAL PRIMARY KEY,
    weapon_id INTEGER NOT NULL REFERENCES weapons(id) ON DELETE CASCADE,
    mode TEXT NOT NULL CHECK (mode IN ('br', 'mp')),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    image_file_id TEXT,
    is_top BOOLEAN NOT NULL DEFAULT FALSE,
    is_season_top BOOLEAN NOT NULL DEFAULT FALSE,
    order_index INTEGER,
    views_count INTEGER DEFAULT 0,
    shares_count INTEGER DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    CONSTRAINT uq_attachment UNIQUE (weapon_id, mode, code)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_attachments_weapon_mode ON attachments (weapon_id, mode);
CREATE INDEX IF NOT EXISTS idx_attachments_is_top ON attachments (weapon_id, mode) WHERE is_top = TRUE;
CREATE INDEX IF NOT EXISTS idx_attachments_code_trgm ON attachments USING gin (code gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_attachments_name_trgm ON attachments USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_attachments_views ON attachments (views_count DESC);

-- ============================================================================
-- STEP 4: Users & Authentication
-- ============================================================================

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    language TEXT DEFAULT 'fa' CHECK (language IN ('fa', 'en')),
    is_banned BOOLEAN DEFAULT FALSE,
    ban_reason TEXT,
    banned_until TIMESTAMP,
    last_seen TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_language ON users (language);
CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users (last_seen DESC);

-- ============================================================================
-- STEP 5: RBAC (Role-Based Access Control)
-- ============================================================================

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    description TEXT,
    icon TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission TEXT NOT NULL,
    PRIMARY KEY (role_id, permission)
);

CREATE TABLE IF NOT EXISTS admins (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    display_name TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_roles (
    user_id BIGINT NOT NULL REFERENCES admins(user_id) ON DELETE CASCADE,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
    assigned_by BIGINT,
    PRIMARY KEY (user_id, role_id)
);

-- ============================================================================
-- STEP 6: User Submissions & Engagement
-- ============================================================================

CREATE TABLE IF NOT EXISTS user_attachments (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    weapon_id INTEGER REFERENCES weapons(id) ON DELETE SET NULL,
    mode TEXT NOT NULL CHECK (mode IN ('br', 'mp')),
    category TEXT,
    custom_weapon_name TEXT,
    attachment_name TEXT NOT NULL,
    description TEXT,
    image_file_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    submitted_at TIMESTAMP NOT NULL DEFAULT NOW(),
    approved_at TIMESTAMP,
    approved_by BIGINT REFERENCES admins(user_id),
    rejected_at TIMESTAMP,
    rejected_by BIGINT REFERENCES admins(user_id),
    rejection_reason TEXT,
    like_count INTEGER NOT NULL DEFAULT 0,
    report_count INTEGER NOT NULL DEFAULT 0,
    views_count INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_user_attachments_status ON user_attachments (status, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_attachments_user ON user_attachments (user_id);
CREATE INDEX IF NOT EXISTS idx_user_attachments_approved ON user_attachments (approved_at DESC) WHERE status = 'approved';

CREATE TABLE IF NOT EXISTS user_submission_stats (
    user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    total_submissions INTEGER NOT NULL DEFAULT 0,
    approved_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    pending_count INTEGER NOT NULL DEFAULT 0,
    daily_submissions INTEGER NOT NULL DEFAULT 0,
    daily_reset_date DATE,
    violation_count INTEGER NOT NULL DEFAULT 0,
    strike_count REAL NOT NULL DEFAULT 0,
    last_submission_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_attachment_engagement (
    user_id BIGINT NOT NULL,
    attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    rating SMALLINT CHECK (rating IN (-1, 1)),
    total_views INTEGER DEFAULT 0,
    total_clicks INTEGER DEFAULT 0,
    first_view_date TIMESTAMP,
    last_view_date TIMESTAMP,
    feedback TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    PRIMARY KEY (user_id, attachment_id)
);

CREATE INDEX IF NOT EXISTS idx_uae_attachment_rating ON user_attachment_engagement (attachment_id, rating);
CREATE INDEX IF NOT EXISTS idx_uae_attachment_views ON user_attachment_engagement (attachment_id, total_views DESC);

CREATE TABLE IF NOT EXISTS user_attachment_reports (
    id SERIAL PRIMARY KEY,
    attachment_id INTEGER NOT NULL REFERENCES user_attachments(id) ON DELETE CASCADE,
    reporter_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'reviewed', 'resolved', 'dismissed')),
    reported_at TIMESTAMP NOT NULL DEFAULT NOW(),
    resolved_by BIGINT REFERENCES admins(user_id),
    resolved_at TIMESTAMP,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_uar_attachment ON user_attachment_reports (attachment_id);
CREATE INDEX IF NOT EXISTS idx_uar_status ON user_attachment_reports (status, reported_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS ux_uar_att_reporter ON user_attachment_reports (attachment_id, reporter_id) WHERE status = 'pending';

-- ============================================================================
-- STEP 7: Support System (Tickets, FAQs, Feedback)
-- ============================================================================

CREATE TABLE IF NOT EXISTS tickets (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category TEXT,
    subject TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'waiting_user', 'resolved', 'closed')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'critical')),
    assigned_to BIGINT REFERENCES admins(user_id),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP,
    closed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets (user_id);
CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets (assigned_to) WHERE assigned_to IS NOT NULL;

CREATE TABLE IF NOT EXISTS ticket_replies (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    attachments TEXT[],
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ticket_replies_ticket ON ticket_replies (ticket_id, created_at);

CREATE TABLE IF NOT EXISTS ticket_attachments (
    id SERIAL PRIMARY KEY,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
    reply_id INTEGER REFERENCES ticket_replies(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL,
    file_type TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS faqs (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category TEXT,
    language TEXT DEFAULT 'fa' CHECK (language IN ('fa', 'en')),
    views INTEGER NOT NULL DEFAULT 0,
    helpful_count INTEGER NOT NULL DEFAULT 0,
    not_helpful_count INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_faqs_category ON faqs (category) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_faqs_language ON faqs (language) WHERE is_active = TRUE;

-- User FAQ votes (for tracking helpful/not helpful votes)
CREATE TABLE IF NOT EXISTS user_faq_votes (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    faq_id INTEGER NOT NULL REFERENCES faqs(id) ON DELETE CASCADE,
    rating SMALLINT CHECK (rating IN (-1, 1)),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, faq_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    category TEXT,
    message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- STEP 8: Search & Analytics
-- ============================================================================

CREATE TABLE IF NOT EXISTS search_history (
    id SERIAL PRIMARY KEY,
    user_id BIGINT,
    query TEXT NOT NULL,
    results_count INTEGER NOT NULL DEFAULT 0,
    execution_time_ms REAL NOT NULL DEFAULT 0,
    search_type TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_search_history_created ON search_history (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history (user_id) WHERE user_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS popular_searches (
    query TEXT PRIMARY KEY,
    search_count INTEGER NOT NULL DEFAULT 0,
    last_searched TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS suggested_attachments (
    attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
    mode TEXT NOT NULL CHECK (mode IN ('br', 'mp')),
    priority INTEGER NOT NULL DEFAULT 999,
    reason TEXT,
    added_by BIGINT REFERENCES admins(user_id),
    added_at TIMESTAMP NOT NULL DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE (attachment_id, mode)
);

CREATE INDEX IF NOT EXISTS idx_suggested_mode_priority ON suggested_attachments (mode, priority) WHERE is_active = TRUE;

-- ============================================================================
-- STEP 9: System Configuration
-- ============================================================================

CREATE TABLE IF NOT EXISTS required_channels (
    channel_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 999,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_required_channels_priority ON required_channels (priority ASC) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS blacklisted_words (
    word TEXT PRIMARY KEY,
    category TEXT NOT NULL DEFAULT 'general',
    severity INTEGER NOT NULL DEFAULT 1 CHECK (severity >= 1 AND severity <= 3),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    description TEXT,
    category TEXT,
    data_type TEXT DEFAULT 'string' CHECK (data_type IN ('string', 'integer', 'boolean', 'json')),
    updated_by BIGINT,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_attachment_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT,
    description TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by BIGINT
);

-- ============================================================================
-- STEP 10: Guides System
-- ============================================================================

CREATE TABLE IF NOT EXISTS guides (
    id SERIAL PRIMARY KEY,
    key TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK (mode IN ('br', 'mp')),
    name TEXT,
    code TEXT,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guide_photos (
    id SERIAL PRIMARY KEY,
    guide_id INTEGER NOT NULL REFERENCES guides(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL,
    caption TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS guide_videos (
    id SERIAL PRIMARY KEY,
    guide_id INTEGER NOT NULL REFERENCES guides(id) ON DELETE CASCADE,
    file_id TEXT NOT NULL,
    caption TEXT,
    sort_order INTEGER DEFAULT 0
);

-- ============================================================================
-- STEP 11: Cache Tables for Performance
-- ============================================================================

CREATE TABLE IF NOT EXISTS ua_stats_cache (
    id INTEGER PRIMARY KEY DEFAULT 1,
    total_attachments INTEGER DEFAULT 0,
    pending_count INTEGER DEFAULT 0,
    approved_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    total_users INTEGER DEFAULT 0,
    active_users INTEGER DEFAULT 0,
    banned_users INTEGER DEFAULT 0,
    br_count INTEGER DEFAULT 0,
    mp_count INTEGER DEFAULT 0,
    total_likes INTEGER DEFAULT 0,
    total_reports INTEGER DEFAULT 0,
    pending_reports INTEGER DEFAULT 0,
    last_week_submissions INTEGER DEFAULT 0,
    last_week_approvals INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT single_row_cache CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS ua_top_weapons_cache (
    weapon_name TEXT NOT NULL,
    mode TEXT,
    attachment_count INTEGER NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ua_top_weapons_count ON ua_top_weapons_cache (attachment_count DESC);

CREATE TABLE IF NOT EXISTS ua_top_users_cache (
    user_id BIGINT NOT NULL,
    username TEXT,
    approved_count INTEGER NOT NULL,
    total_likes INTEGER NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ua_top_users_approved ON ua_top_users_cache (approved_count DESC);

-- ============================================================================
-- STEP 12: Data Health & Quality
-- ============================================================================

CREATE TABLE IF NOT EXISTS data_health_checks (
    id SERIAL PRIMARY KEY,
    check_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    category TEXT,
    issue_count INTEGER NOT NULL DEFAULT 0,
    details JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_checks_created ON data_health_checks (created_at DESC);

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

-- ============================================================================
-- STEP 13: Seed Default Data
-- ============================================================================

-- Insert default weapon categories
INSERT INTO weapon_categories (name, display_name, sort_order) VALUES
    ('assault_rifle', 'Assault Rifle', 1),
    ('smg', 'SMG', 2),
    ('lmg', 'LMG', 3),
    ('sniper', 'Sniper', 4),
    ('marksman', 'Marksman', 5),
    ('shotgun', 'Shotgun', 6),
    ('pistol', 'Pistol', 7),
    ('launcher', 'Launcher', 8)
ON CONFLICT (name) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    sort_order = EXCLUDED.sort_order;

-- Insert default roles
INSERT INTO roles (name, display_name, description) VALUES
    ('super_admin', 'Super Admin', 'Full system access'),
    ('admin', 'Admin', 'General administrative access'),
    ('moderator', 'Moderator', 'Content moderation access'),
    ('support', 'Support', 'User support access')
ON CONFLICT (name) DO NOTHING;

-- Insert default permissions
INSERT INTO role_permissions (role_id, permission) 
SELECT r.id, p.perm FROM roles r, 
    (VALUES 
        ('super_admin', 'all'),
        ('admin', 'manage_attachments'),
        ('admin', 'manage_users'),
        ('admin', 'view_analytics'),
        ('moderator', 'moderate_content'),
        ('moderator', 'manage_reports'),
        ('support', 'manage_tickets'),
        ('support', 'manage_faqs')
    ) AS p(role, perm)
WHERE r.name = p.role
ON CONFLICT DO NOTHING;

-- Initialize cache
INSERT INTO ua_stats_cache (id) VALUES (1) ON CONFLICT DO NOTHING;

-- ============================================================================
-- STEP 14: Grant Permissions & Ownership
-- ============================================================================

-- Grant all privileges
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO codm_bot_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO codm_bot_user;
GRANT USAGE ON SCHEMA public TO codm_bot_user;

-- Transfer ownership of all tables to codm_bot_user
DO $$
DECLARE
    tbl RECORD;
BEGIN
    FOR tbl IN SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER TABLE %I OWNER TO codm_bot_user', tbl.tablename);
    END LOOP;
END
$$;

-- Transfer ownership of all sequences to codm_bot_user
DO $$
DECLARE
    seq RECORD;
BEGIN
    FOR seq IN SELECT sequencename FROM pg_sequences WHERE schemaname = 'public'
    LOOP
        EXECUTE format('ALTER SEQUENCE %I OWNER TO codm_bot_user', seq.sequencename);
    END LOOP;
END
$$;

-- ============================================================================
-- END OF SETUP
-- ============================================================================
