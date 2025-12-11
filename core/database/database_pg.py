"""
PostgreSQL Database Wrapper
این wrapper تمام عملیات DatabaseSQL را با PostgreSQL پیاده‌سازی می‌کند
"""

import os
import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from typing import Dict, List, Optional, Any, Tuple
from contextlib import contextmanager
from utils.logger import get_logger, log_exception
from utils.metrics import measure_query_time
import time
import logging

logger = get_logger('database.postgres', 'database.log')


class QueryConverter:
    """تبدیل queries به PostgreSQL format"""
    
    @staticmethod
    def convert(query: str) -> str:
        """
        تبدیل query به PostgreSQL format
        
        Changes:
        - legacy placeholders → %s
        - AUTOINCREMENT → SERIAL
        - datetime('now') → NOW()
        """
        converted = query.replace('$PH$', '%s')
        converted = converted.replace('AUTOINCREMENT', 'SERIAL')
        converted = converted.replace("datetime('now')", 'NOW()')
        converted = converted.replace("datetime()", 'NOW()')
        
        return converted


class DatabasePostgres:
    """
    PostgreSQL Database Handler
    Compatible با DatabaseSQL interface - تمام متدها را دارد
    """
    
    def __init__(self, database_url: str = None):
        """
        Initialize PostgreSQL connection pool
        
        Args:
            database_url: PostgreSQL connection string
        """
        if database_url is None:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise ValueError("DATABASE_URL is required for PostgreSQL")
        
        self.database_url = database_url
        self.db_path = database_url.split('@')[-1] if '@' in database_url else database_url
        
        # Connection pool settings
        pool_size = int(os.getenv('DB_POOL_SIZE', 20))
        max_overflow = int(os.getenv('DB_POOL_MAX_OVERFLOW', 10))
        
        try:
            # Create connection pool (psycopg3 style)
            self._pool = ConnectionPool(
                conninfo=database_url,
                min_size=2,
                max_size=pool_size + max_overflow,
                kwargs={'row_factory': dict_row},
                open=True
            )
            
            logger.info(f"PostgreSQL connection pool initialized: {pool_size} connections")
            
            # Test connection
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version() as version")
                result = cursor.fetchone()
                version = result['version'] if result else 'unknown'
                logger.info(f"Connected to: {version.split(',')[0]}")
                cursor.close()
            
            # Initialize fuzzy search
            self.fuzzy_engine = None
            self._init_fuzzy_engine()
            
            # Ensure critical schema elements exist (non-destructive)
            self._ensure_schema()
            
            logger.info("DatabasePostgres initialized successfully")
            
        except psycopg.Error as e:
            logger.error(f"PostgreSQL connection error: {e}")
            log_exception(logger, e, "DatabasePostgres.__init__")
            raise
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL: {e}")
            log_exception(logger, e, "DatabasePostgres.__init__")
            raise
    
    @contextmanager
    def get_connection(self):
        """Context manager برای دریافت connection از pool"""
        with self._pool.connection() as conn:
            yield conn
    
    @property
    def connection(self):
        """
        دسترسی به connection (برای backward compatibility)
        
        Warning: psycopg3 pool نیاز به context manager دارد
        برای read-only queries از get_connection() استفاده کنید
        """
        # برای backward compatibility، یک connection می‌گیریم
        # اما توصیه می‌شود از get_connection() context manager استفاده شود
        logger.warning("Direct connection access - use get_connection() context manager instead")
        return self._pool.connection()
    
    @contextmanager
    def transaction(self):
        """
        Context manager برای transaction
        Compatible با DatabaseSQL.transaction()
        """
        with self.get_connection() as conn:
            try:
                yield conn
                conn.commit()
            except psycopg.Error as e:
                conn.rollback()
                logger.error(f"PostgreSQL transaction error: {e}")
                log_exception(logger, e, "transaction")
                raise
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction error: {e}")
                log_exception(logger, e, "transaction")
                raise
    
    def close(self) -> None:
        """بستن ایمن کانکشن‌پول PostgreSQL.
        
        این متد برای هماهنگی با `DatabaseAdapter.close` پیاده‌سازی شده تا در خاموشی،
        منابع دیتابیس به‌درستی آزاد شوند.
        """
        try:
            if hasattr(self, "_pool") and self._pool:
                # Close the pool; ignore exceptions to avoid masking shutdown flow
                try:
                    self._pool.close()
                except Exception:
                    pass
                # psycopg_pool provides wait_close() in newer versions
                try:
                    wait_close = getattr(self._pool, "wait_close", None)
                    if callable(wait_close):
                        wait_close()
                except Exception:
                    pass
            logger.info("PostgreSQL connection pool closed")
        except Exception as e:
            logger.error(f"Error closing PostgreSQL pool: {e}")
    
    def execute_query(self, query: str, params: tuple = None, fetch_one: bool = False, 
                     fetch_all: bool = False, as_dict: bool = True) -> Any:
        """
        اجرای query با تبدیل خودکار placeholders و tracking performance
        
        Args:
            query: SQL query
            params: پارامترها
            fetch_one: برگرداندن یک رکورد
            fetch_all: برگرداندن همه رکوردها
            as_dict: نتیجه به صورت dict
        """
        # تبدیل query
        converted_query = QueryConverter.convert(query)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            try:
                # اندازه‌گیری زمان query با metrics
                with measure_query_time(converted_query[:200], params):
                    cursor.execute(converted_query, params or ())
                
                if fetch_one:
                    result = cursor.fetchone()
                    return dict(result) if result and as_dict else result
                elif fetch_all:
                    results = cursor.fetchall()
                    return [dict(r) for r in results] if as_dict else results
                else:
                    conn.commit()
                    return cursor.rowcount
                    
            except psycopg.Error as e:
                conn.rollback()
                logger.error(f"PostgreSQL query error: {e}")
                logger.error(f"Query: {converted_query[:200]}")
                logger.error(f"Params: {params}")
                raise
            except Exception as e:
                conn.rollback()
                logger.error(f"Query execution error: {e}")
                logger.error(f"Query: {converted_query[:200]}")
                raise
            finally:
                cursor.close()
    
    def _init_fuzzy_engine(self):
        """راه‌اندازی fuzzy search (compatible با DatabaseSQL)"""
        try:
            from utils.search_fuzzy import FuzzySearchEngine
            self.fuzzy_engine = FuzzySearchEngine(self)
            logger.info("Fuzzy search engine initialized")
        except ImportError:
            logger.warning("FuzzySearchEngine not available")
        except Exception as e:
            logger.error(f"Failed to initialize fuzzy search: {e}")
    
    def _ensure_schema(self):
        """
        Ensure required columns/tweaks exist on PostgreSQL schema.
        This is a safe, idempotent guard that runs at startup.
        Currently ensures:
        - attachments.updated_at TIMESTAMPTZ
        - attachments.order_index INTEGER (nullable)
        - pg_trgm extension and trigram GIN indexes for attachments.name/code
        - analytics tables alignment (popular_searches.search_count, search_history.execution_time_ms)
        """
        try:
            with self.get_connection() as conn:
                # CRITICAL: Use autocommit to prevent transaction abort cascade
                conn.autocommit = True
                cursor = conn.cursor()
                # Helper to check if a column exists
                def _column_exists(table: str, column: str) -> bool:
                    cursor.execute(
                        """
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = %s
                          AND column_name = %s
                        """,
                        (table, column),
                    )
                    return cursor.fetchone() is not None
                # Helper to check if a table exists
                def _table_exists(table: str) -> bool:
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1
                            FROM information_schema.tables
                            WHERE table_schema = current_schema()
                              AND table_name = %s
                        ) AS exists
                        """,
                        (table,),
                    )
                    row = cursor.fetchone()
                    return bool(row.get('exists')) if row else False

                # ============================================================================
                # COMPREHENSIVE SCHEMA CREATION (Self-Healing)
                # ============================================================================
                
                # 1. Extensions
                try:
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
                except Exception as e:
                    logger.warning(f"ensure_schema(extensions) warning: {e}")

                # 2. Core Tables (Order matters due to foreign keys)
                tables_sql = [
                    # Weapon Categories
                    """
                    CREATE TABLE IF NOT EXISTS weapon_categories (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        display_name TEXT,
                        icon TEXT,
                        sort_order INTEGER DEFAULT 0,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Weapons
                    """
                    CREATE TABLE IF NOT EXISTS weapons (
                        id SERIAL PRIMARY KEY,
                        category_id INTEGER NOT NULL REFERENCES weapon_categories(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        display_name TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP,
                        UNIQUE (category_id, name)
                    )
                    """,
                    # Attachments
                    """
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
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        CONSTRAINT uq_attachment UNIQUE (weapon_id, mode, code)
                    )
                    """,
                    # Users
                    """
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
                    )
                    """,
                    # Roles
                    """
                    CREATE TABLE IF NOT EXISTS roles (
                        id SERIAL PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE,
                        display_name TEXT NOT NULL,
                        description TEXT,
                        icon TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP
                    )
                    """,
                    # Role Permissions
                    """
                    CREATE TABLE IF NOT EXISTS role_permissions (
                        role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                        permission TEXT NOT NULL,
                        PRIMARY KEY (role_id, permission)
                    )
                    """,
                    # Admins
                    """
                    CREATE TABLE IF NOT EXISTS admins (
                        user_id BIGINT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
                        display_name TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP
                    )
                    """,
                    # Admin Roles
                    """
                    CREATE TABLE IF NOT EXISTS admin_roles (
                        user_id BIGINT NOT NULL REFERENCES admins(user_id) ON DELETE CASCADE,
                        role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
                        assigned_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        assigned_by BIGINT,
                        PRIMARY KEY (user_id, role_id)
                    )
                    """,
                    # User Attachments
                    """
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
                    )
                    """,
                    # User Submission Stats
                    """
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
                        updated_at TIMESTAMP,
                        is_banned BOOLEAN NOT NULL DEFAULT FALSE,
                        banned_reason TEXT,
                        banned_at TIMESTAMP
                    )
                    """,
                    # User Attachment Engagement
                    """
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
                    )
                    """,
                    # User Attachment Reports
                    """
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
                    )
                    """,
                    # Tickets
                    """
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
                    )
                    """,
                    # Ticket Replies
                    """
                    CREATE TABLE IF NOT EXISTS ticket_replies (
                        id SERIAL PRIMARY KEY,
                        ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                        user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                        message TEXT NOT NULL,
                        is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                        attachments TEXT[],
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Ticket Attachments
                    """
                    CREATE TABLE IF NOT EXISTS ticket_attachments (
                        id SERIAL PRIMARY KEY,
                        ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
                        reply_id INTEGER REFERENCES ticket_replies(id) ON DELETE CASCADE,
                        file_id TEXT NOT NULL,
                        file_type TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # FAQs
                    """
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
                    )
                    """,
                    # Feedback
                    """
                    CREATE TABLE IF NOT EXISTS feedback (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id) ON DELETE SET NULL,
                        rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
                        category TEXT,
                        message TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Search History
                    """
                    CREATE TABLE IF NOT EXISTS search_history (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        query TEXT NOT NULL,
                        results_count INTEGER NOT NULL DEFAULT 0,
                        execution_time_ms REAL NOT NULL DEFAULT 0,
                        search_type TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Popular Searches
                    """
                    CREATE TABLE IF NOT EXISTS popular_searches (
                        query TEXT PRIMARY KEY,
                        search_count INTEGER NOT NULL DEFAULT 0,
                        last_searched TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Suggested Attachments
                    """
                    CREATE TABLE IF NOT EXISTS suggested_attachments (
                        attachment_id INTEGER NOT NULL REFERENCES attachments(id) ON DELETE CASCADE,
                        mode TEXT NOT NULL CHECK (mode IN ('br', 'mp')),
                        priority INTEGER NOT NULL DEFAULT 999,
                        reason TEXT,
                        added_by BIGINT REFERENCES admins(user_id),
                        added_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        is_active BOOLEAN DEFAULT TRUE,
                        UNIQUE (attachment_id, mode)
                    )
                    """,
                    # Required Channels
                    """
                    CREATE TABLE IF NOT EXISTS required_channels (
                        channel_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        url TEXT NOT NULL,
                        priority INTEGER NOT NULL DEFAULT 999,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP
                    )
                    """,
                    # Blacklisted Words
                    """
                    CREATE TABLE IF NOT EXISTS blacklisted_words (
                        word TEXT PRIMARY KEY,
                        category TEXT NOT NULL DEFAULT 'general',
                        severity INTEGER NOT NULL DEFAULT 1 CHECK (severity >= 1 AND severity <= 3),
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Settings
                    """
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        description TEXT,
                        category TEXT,
                        data_type TEXT DEFAULT 'string' CHECK (data_type IN ('string', 'integer', 'boolean', 'json')),
                        updated_by BIGINT,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # User Attachment Settings
                    """
                    CREATE TABLE IF NOT EXISTS user_attachment_settings (
                        setting_key TEXT PRIMARY KEY,
                        setting_value TEXT,
                        description TEXT,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                        updated_by BIGINT
                    )
                    """,
                    # Bot Settings
                    """
                    CREATE TABLE IF NOT EXISTS bot_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        description TEXT,
                        updated_at TIMESTAMP DEFAULT NOW()
                    )
                    """,
                    # Guides
                    """
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
                    )
                    """,
                    # Guide Photos
                    """
                    CREATE TABLE IF NOT EXISTS guide_photos (
                        id SERIAL PRIMARY KEY,
                        guide_id INTEGER NOT NULL REFERENCES guides(id) ON DELETE CASCADE,
                        file_id TEXT NOT NULL,
                        caption TEXT,
                        sort_order INTEGER DEFAULT 0
                    )
                    """,
                    # Guide Videos
                    """
                    CREATE TABLE IF NOT EXISTS guide_videos (
                        id SERIAL PRIMARY KEY,
                        guide_id INTEGER NOT NULL REFERENCES guides(id) ON DELETE CASCADE,
                        file_id TEXT NOT NULL,
                        caption TEXT,
                        sort_order INTEGER DEFAULT 0
                    )
                    """,
                    # UA Stats Cache
                    """
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
                    )
                    """,
                    # UA Top Weapons Cache
                    """
                    CREATE TABLE IF NOT EXISTS ua_top_weapons_cache (
                        weapon_name TEXT NOT NULL,
                        mode TEXT,
                        attachment_count INTEGER NOT NULL,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # UA Top Users Cache
                    """
                    CREATE TABLE IF NOT EXISTS ua_top_users_cache (
                        user_id BIGINT NOT NULL,
                        username TEXT,
                        approved_count INTEGER NOT NULL,
                        total_likes INTEGER NOT NULL,
                        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Data Health Checks
                    """
                    CREATE TABLE IF NOT EXISTS data_health_checks (
                        id SERIAL PRIMARY KEY,
                        check_type TEXT NOT NULL,
                        severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error', 'critical')),
                        category TEXT,
                        issue_count INTEGER NOT NULL DEFAULT 0,
                        details JSONB,
                        created_at TIMESTAMP NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Data Quality Metrics
                    """
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
                    )
                    """,
                    # User Notification Preferences
                    """
                    CREATE TABLE IF NOT EXISTS user_notification_preferences (
                        user_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        modes JSONB NOT NULL DEFAULT '["br","mp"]'::jsonb,
                        events JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Scheduled Notifications
                    """
                    CREATE TABLE IF NOT EXISTS scheduled_notifications (
                        id SERIAL PRIMARY KEY,
                        message_type TEXT NOT NULL CHECK (message_type IN ('text','photo')),
                        message_text TEXT,
                        photo_file_id TEXT,
                        parse_mode TEXT DEFAULT 'Markdown',
                        interval_hours INTEGER NOT NULL,
                        enabled BOOLEAN NOT NULL DEFAULT TRUE,
                        last_sent_at TIMESTAMPTZ,
                        next_run_at TIMESTAMPTZ NOT NULL,
                        created_by BIGINT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Attachment Metrics
                    """
                    CREATE TABLE IF NOT EXISTS attachment_metrics (
                        id SERIAL PRIMARY KEY,
                        attachment_id INTEGER NOT NULL,
                        user_id BIGINT,
                        action_type TEXT NOT NULL CHECK (action_type IN ('view','click','share','copy','rate')),
                        session_id TEXT,
                        metadata JSONB,
                        action_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """,
                    # Attachment Performance
                    """
                    CREATE TABLE IF NOT EXISTS attachment_performance (
                        attachment_id INTEGER NOT NULL,
                        performance_date DATE NOT NULL,
                        popularity_score REAL NOT NULL DEFAULT 0,
                        trending_score REAL NOT NULL DEFAULT 0,
                        engagement_rate REAL NOT NULL DEFAULT 0,
                        quality_score REAL NOT NULL DEFAULT 0,
                        rank_in_weapon INTEGER,
                        rank_overall INTEGER,
                        PRIMARY KEY (attachment_id, performance_date)
                    )
                    """,
                    # CMS Content
                    """
                    CREATE TABLE IF NOT EXISTS cms_content (
                        content_id SERIAL PRIMARY KEY,
                        content_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        body TEXT NOT NULL,
                        tags JSONB NOT NULL DEFAULT '[]'::jsonb,
                        author_id BIGINT,
                        status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','published','archived')),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        published_at TIMESTAMPTZ
                    )
                    """
                ]

                for sql in tables_sql:
                    try:
                        cursor.execute(sql)
                    except Exception as e:
                        logger.warning(f"ensure_schema(create table) warning: {e}")

                # 3. Indexes (Helpful indexes)
                indexes_sql = [
                    "CREATE INDEX IF NOT EXISTS idx_attachments_weapon_mode ON attachments (weapon_id, mode)",
                    "CREATE INDEX IF NOT EXISTS idx_attachments_is_top ON attachments (weapon_id, mode) WHERE is_top = TRUE",
                    "CREATE INDEX IF NOT EXISTS idx_attachments_code_trgm ON attachments USING gin (code gin_trgm_ops)",
                    "CREATE INDEX IF NOT EXISTS idx_attachments_name_trgm ON attachments USING gin (name gin_trgm_ops)",
                    "CREATE INDEX IF NOT EXISTS idx_attachments_views ON attachments (views_count DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_users_language ON users (language)",
                    "CREATE INDEX IF NOT EXISTS idx_users_last_seen ON users (last_seen DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_user_attachments_status ON user_attachments (status, submitted_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_user_attachments_user ON user_attachments (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_user_attachments_approved ON user_attachments (approved_at DESC) WHERE status = 'approved'",
                    "CREATE INDEX IF NOT EXISTS idx_uae_attachment_rating ON user_attachment_engagement (attachment_id, rating)",
                    "CREATE INDEX IF NOT EXISTS idx_uae_attachment_views ON user_attachment_engagement (attachment_id, total_views DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_uar_attachment ON user_attachment_reports (attachment_id)",
                    "CREATE INDEX IF NOT EXISTS idx_uar_status ON user_attachment_reports (status, reported_at DESC)",
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_uar_att_reporter ON user_attachment_reports (attachment_id, reporter_id) WHERE status = 'pending'",
                    "CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets (status, created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets (user_id)",
                    "CREATE INDEX IF NOT EXISTS idx_tickets_assigned ON tickets (assigned_to) WHERE assigned_to IS NOT NULL",
                    "CREATE INDEX IF NOT EXISTS idx_ticket_replies_ticket ON ticket_replies (ticket_id, created_at)",
                    "CREATE INDEX IF NOT EXISTS idx_faqs_category ON faqs (category) WHERE is_active = TRUE",
                    "CREATE INDEX IF NOT EXISTS idx_faqs_language ON faqs (language) WHERE is_active = TRUE",
                    "CREATE INDEX IF NOT EXISTS idx_search_history_created ON search_history (created_at DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_search_history_user ON search_history (user_id) WHERE user_id IS NOT NULL",
                    "CREATE INDEX IF NOT EXISTS idx_suggested_mode_priority ON suggested_attachments (mode, priority) WHERE is_active = TRUE",
                    "CREATE INDEX IF NOT EXISTS idx_required_channels_priority ON required_channels (priority ASC) WHERE is_active = TRUE",
                    "CREATE INDEX IF NOT EXISTS idx_ua_top_weapons_count ON ua_top_weapons_cache (attachment_count DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_ua_top_users_approved ON ua_top_users_cache (approved_count DESC)",
                    "CREATE INDEX IF NOT EXISTS idx_health_checks_created ON data_health_checks (created_at DESC)",
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_attachments_weapon_mode_code ON attachments (weapon_id, mode, code)",
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_suggested_attachment_mode ON suggested_attachments (attachment_id, mode)",
                    "CREATE INDEX IF NOT EXISTS ix_suggested_mode ON suggested_attachments (mode)",
                    "CREATE INDEX IF NOT EXISTS ix_uae_attachment_id ON user_attachment_engagement (attachment_id)",
                    "CREATE INDEX IF NOT EXISTS ix_uae_attachment_id_rating ON user_attachment_engagement (attachment_id, rating)",
                    "CREATE INDEX IF NOT EXISTS ix_ticket_attachments_ticket_id ON ticket_attachments (ticket_id)",
                    "CREATE INDEX IF NOT EXISTS ix_ticket_attachments_reply_id ON ticket_attachments (reply_id)",
                    "CREATE INDEX IF NOT EXISTS ix_sched_notif_next_run ON scheduled_notifications (next_run_at)",
                    "CREATE INDEX IF NOT EXISTS ix_sched_notif_enabled_next ON scheduled_notifications (enabled, next_run_at)",
                    "CREATE INDEX IF NOT EXISTS ix_am_attachment_date ON attachment_metrics (attachment_id, action_date)",
                    "CREATE INDEX IF NOT EXISTS ix_am_action_date ON attachment_metrics (action_type, action_date)",
                    "CREATE INDEX IF NOT EXISTS ix_am_attachment_action ON attachment_metrics (attachment_id, action_type)",
                    "CREATE INDEX IF NOT EXISTS ix_am_user ON attachment_metrics (user_id)",
                    "CREATE INDEX IF NOT EXISTS ix_uae_attachment ON user_attachment_engagement (attachment_id)",
                    "CREATE INDEX IF NOT EXISTS ix_cms_content_status_pub ON cms_content (status, published_at DESC)",
                    "CREATE INDEX IF NOT EXISTS ix_cms_content_type_status ON cms_content (content_type, status)",
                    "CREATE INDEX IF NOT EXISTS ix_cms_content_tags_gin ON cms_content USING gin (tags)"
                ]

                for sql in indexes_sql:
                    try:
                        cursor.execute(sql)
                    except Exception as e:
                        logger.warning(f"ensure_schema(create index) warning: {e}")

                # 4. Seed Data (Default values)
                try:
                    # Weapon Categories
                    cursor.execute("""
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
                            sort_order = EXCLUDED.sort_order
                    """)
                    
                    # Roles
                    cursor.execute("""
                        INSERT INTO roles (name, display_name, description) VALUES
                            ('super_admin', 'Super Admin', 'Full system access'),
                            ('admin', 'Admin', 'General administrative access'),
                            ('moderator', 'Moderator', 'Content moderation access'),
                            ('support', 'Support', 'User support access')
                        ON CONFLICT (name) DO NOTHING
                    """)
                    
                    # Permissions
                    cursor.execute("""
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
                        ON CONFLICT DO NOTHING
                    """)
                    
                    # Default Settings
                    cursor.execute("""
                        INSERT INTO user_attachment_settings (setting_key, setting_value, description)
                        VALUES ('system_enabled', 'true', 'Enable/Disable User Attachments System')
                        ON CONFLICT (setting_key) DO NOTHING
                    """)
                    
                    # Initialize Cache
                    cursor.execute("INSERT INTO ua_stats_cache (id) VALUES (1) ON CONFLICT DO NOTHING")
                    
                except Exception as e:
                    logger.warning(f"ensure_schema(seed data) warning: {e}")

                logger.info("Database schema ensured successfully")
        except Exception as e:
            logger.error(f"Database schema check failed: {e}")

    def get_users_for_notification(self, event_types: list, mode: str) -> set:
        """
        Get active users for notification efficiently using SQL
        
        Args:
            event_types: List of event types to check (OR logic)
            mode: Game mode (mp/br)
            
        Returns:
            Set of user_ids
        """
        query = """
            SELECT s.user_id
            FROM subscribers s
            LEFT JOIN user_preferences up ON s.user_id = up.user_id
            WHERE 
                -- 1. User has no preferences (default enabled)
                up.user_id IS NULL
                OR
                (
                    -- 2. Global enabled check
                    COALESCE((up.preferences->>'enabled')::boolean, true) = true
                    AND
                    -- 3. Mode check
                    (up.preferences->'modes') @> to_jsonb(%s::text)
                    AND
                    -- 4. Event check (at least one event must be enabled)
                    (
                        -- If events object is missing, default is true
                        up.preferences->'events' IS NULL
                        OR
                        EXISTS (
                            SELECT 1
                            FROM jsonb_each_text(up.preferences->'events')
                            WHERE key = ANY(%s) AND value::boolean = true
                        )
                        OR
                        -- If any of the requested events are NOT in the events object, they are true by default
                        EXISTS (
                            SELECT 1
                            FROM unnest(%s::text[]) as req_event
                            WHERE NOT (up.preferences->'events' ? req_event)
                        )
                    )
                )
        """
        
        try:
            # Convert mode to json string for containment check
            mode_json = f'"{mode}"'
            
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (mode_json, event_types, event_types))
                results = cursor.fetchall()
                return {row['user_id'] for row in results}
                
        except Exception as e:
            logger.error(f"Error fetching notification users: {e}")
            # Fallback to empty set to avoid spamming everyone on error
            return set()

    def close(self):
        """بستن connection pool"""
        if hasattr(self, '_pool'):
            try:
                # Wait for workers to finish, then close (timeouts configurable)
                try:
                    wait_timeout = float(os.getenv('DB_POOL_WAIT_TIMEOUT', '2'))
                except Exception:
                    wait_timeout = 2.0
                try:
                    close_timeout = float(os.getenv('DB_POOL_CLOSE_TIMEOUT', '10'))
                except Exception:
                    close_timeout = 10.0
                # Optionally suppress psycopg.pool warnings during shutdown
                suppress_warn = str(os.getenv('DB_SUPPRESS_POOL_WARNINGS', 'false')).lower() in ('1', 'true', 'yes')
                pool_logger = logging.getLogger('psycopg.pool')
                previous_level = pool_logger.level if suppress_warn else None
                if suppress_warn:
                    try:
                        pool_logger.setLevel(logging.ERROR)
                    except Exception:
                        pass
                self._pool.wait(timeout=wait_timeout)
                self._pool.close(timeout=close_timeout)
                logger.info("PostgreSQL connection pool closed gracefully")
            except Exception as e:
                # اگر timeout شد، force close
                try:
                    self._pool.close(timeout=0)
                except Exception as close_exc:
                    logger.warning(f"Error forcing PostgreSQL pool close: {close_exc}")
                logger.debug(f"Connection pool forced close: {e}")
            finally:
                # Restore logger level
                if 'suppress_warn' in locals() and suppress_warn and previous_level is not None:
                    try:
                        pool_logger.setLevel(previous_level)
                    except Exception:
                        pass
    
    def __del__(self):
        """Cleanup"""
        try:
            self.close()
        except Exception as e:
            # در مرحله جمع‌آوری اشیاء، فقط هشدار سبک ثبت می‌کنیم
            logger.debug(f"Error during DatabasePostgres __del__ cleanup: {e}")


# ==============================================================================
# Singleton
# ==============================================================================

_instance = None

def get_postgres_instance(database_url: str = None) -> DatabasePostgres:
    """دریافت instance singleton"""
    global _instance
    
    if _instance is None:
        _instance = DatabasePostgres(database_url)
        
        # Register cleanup
        import atexit
        atexit.register(_instance.close)
    
    return _instance
