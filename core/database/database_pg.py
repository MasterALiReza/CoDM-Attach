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

                # 0) users.language and users.last_seen (compatibility with adapters)
                try:
                    # language TEXT DEFAULT 'fa'
                    if _table_exists('users'):
                        if not _column_exists('users', 'language'):
                            cursor.execute(
                                "ALTER TABLE users ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'fa'"
                            )
                            logger.info("Added missing column: users.language")
                        # backfill nulls
                        try:
                            cursor.execute(
                                "UPDATE users SET language = 'fa' WHERE language IS NULL"
                            )
                        except Exception:
                            pass
                        # last_seen TIMESTAMP (nullable)
                        if not _column_exists('users', 'last_seen'):
                            cursor.execute(
                                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP"
                            )
                            logger.info("Added missing column: users.last_seen")
                except Exception as e:
                    logger.warning(f"ensure_schema(users columns) warning: {e}")

                # 1) attachments.updated_at
                try:
                    if not _column_exists('attachments', 'updated_at'):
                        cursor.execute(
                            "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"
                        )
                        logger.info("Added missing column: attachments.updated_at")
                    # Backfill nulls to NOW()
                    cursor.execute(
                        "UPDATE attachments SET updated_at = NOW() WHERE updated_at IS NULL"
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(updated_at) warning: {e}")

                # 2) attachments.order_index (nullable integer used for top ordering)
                try:
                    if not _column_exists('attachments', 'order_index'):
                        cursor.execute(
                            "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS order_index INTEGER"
                        )
                        logger.info("Added missing column: attachments.order_index")
                except Exception as e:
                    logger.warning(f"ensure_schema(order_index) warning: {e}")

                # 2.5) Ensure pg_trgm extension and GIN trigram indexes for better search
                try:
                    try:
                        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                    except Exception as ext_err:
                        logger.warning(f"pg_trgm extension ensure failed (non-fatal): {ext_err}")
                    # GIN trigram indexes on attachments.name/code
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_attachments_name_trgm ON attachments USING gin (name gin_trgm_ops)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS idx_attachments_code_trgm ON attachments USING gin (code gin_trgm_ops)"
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(trgm indexes) warning: {e}")

                # 3) Ensure unique index for ON CONFLICT (weapon_id, mode, code)
                try:
                    cursor.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ux_attachments_weapon_mode_code ON attachments (weapon_id, mode, code)"
                    )
                    logger.info("Ensured unique index: ux_attachments_weapon_mode_code")
                except Exception as e:
                    logger.warning(f"ensure_schema(unique_index) warning: {e}")

                # 3.1) Helpful index for filtering/joining attachments by weapon and mode
                try:
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_attachments_weapon_mode ON attachments (weapon_id, mode)"
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(ix_attachments_weapon_mode) warning: {e}")

                # 3.2) Suggested attachments indexes (speed up counts and uniqueness)
                try:
                    cursor.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS ux_suggested_attachment_mode ON suggested_attachments (attachment_id, mode)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_suggested_mode ON suggested_attachments (mode)"
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(suggested indexes) warning: {e}")

                # 3.3) Engagement table indexes for faster aggregation in analytics
                try:
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_uae_attachment_id ON user_attachment_engagement (attachment_id)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_uae_attachment_id_rating ON user_attachment_engagement (attachment_id, rating)"
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(uae indexes) warning: {e}")

                # 4) user_submission_stats required columns (for UA system)
                try:
                    # is_banned BOOLEAN NOT NULL DEFAULT FALSE
                    if not _column_exists('user_submission_stats', 'is_banned'):
                        cursor.execute(
                            "ALTER TABLE user_submission_stats ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE"
                        )
                        logger.info("Added missing column: user_submission_stats.is_banned")
                    cursor.execute(
                        "ALTER TABLE user_submission_stats ALTER COLUMN is_banned SET DEFAULT FALSE"
                    )
                    # backfill nulls and enforce NOT NULL
                    cursor.execute(
                        "UPDATE user_submission_stats SET is_banned = FALSE WHERE is_banned IS NULL"
                    )
                    cursor.execute(
                        "ALTER TABLE user_submission_stats ALTER COLUMN is_banned SET NOT NULL"
                    )

                    # daily_submissions INTEGER NOT NULL DEFAULT 0
                    if not _column_exists('user_submission_stats', 'daily_submissions'):
                        cursor.execute(
                            "ALTER TABLE user_submission_stats ADD COLUMN IF NOT EXISTS daily_submissions INTEGER DEFAULT 0"
                        )
                        logger.info("Added missing column: user_submission_stats.daily_submissions")
                    cursor.execute(
                        "ALTER TABLE user_submission_stats ALTER COLUMN daily_submissions SET DEFAULT 0"
                    )
                    cursor.execute(
                        "UPDATE user_submission_stats SET daily_submissions = 0 WHERE daily_submissions IS NULL"
                    )
                    cursor.execute(
                        "ALTER TABLE user_submission_stats ALTER COLUMN daily_submissions SET NOT NULL"
                    )

                    # daily_reset_date DATE
                    if not _column_exists('user_submission_stats', 'daily_reset_date'):
                        cursor.execute(
                            "ALTER TABLE user_submission_stats ADD COLUMN IF NOT EXISTS daily_reset_date DATE"
                        )
                        logger.info("Added missing column: user_submission_stats.daily_reset_date")

                    # banned_reason TEXT
                    if not _column_exists('user_submission_stats', 'banned_reason'):
                        cursor.execute(
                            "ALTER TABLE user_submission_stats ADD COLUMN IF NOT EXISTS banned_reason TEXT"
                        )
                        logger.info("Added missing column: user_submission_stats.banned_reason")

                    # banned_at TIMESTAMP
                    if not _column_exists('user_submission_stats', 'banned_at'):
                        cursor.execute(
                            "ALTER TABLE user_submission_stats ADD COLUMN IF NOT EXISTS banned_at TIMESTAMP"
                        )
                        logger.info("Added missing column: user_submission_stats.banned_at")
                except Exception as e:
                    logger.warning(f"ensure_schema(user_submission_stats) warning: {e}")

                # 4.5) user_notification_preferences table (for per-user notification settings)
                try:
                    if not _table_exists('user_notification_preferences'):
                        cursor.execute(
                            """
                            CREATE TABLE IF NOT EXISTS user_notification_preferences (
                              user_id BIGINT PRIMARY KEY,
                              enabled BOOLEAN NOT NULL DEFAULT TRUE,
                              modes JSONB NOT NULL DEFAULT '["br","mp"]'::jsonb,
                              events JSONB NOT NULL DEFAULT '{}'::jsonb,
                              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        logger.info("Created table: user_notification_preferences")
                    else:
                        # Legacy installs: ensure required columns exist with sane defaults
                        if not _column_exists('user_notification_preferences', 'enabled'):
                            cursor.execute(
                                "ALTER TABLE user_notification_preferences ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE"
                            )
                        if not _column_exists('user_notification_preferences', 'modes'):
                            cursor.execute(
                                "ALTER TABLE user_notification_preferences ADD COLUMN IF NOT EXISTS modes JSONB NOT NULL DEFAULT '[""br"",""mp""]'::jsonb"
                            )
                        if not _column_exists('user_notification_preferences', 'events'):
                            cursor.execute(
                                "ALTER TABLE user_notification_preferences ADD COLUMN IF NOT EXISTS events JSONB NOT NULL DEFAULT '{}'::jsonb"
                            )
                        if not _column_exists('user_notification_preferences', 'updated_at'):
                            cursor.execute(
                                "ALTER TABLE user_notification_preferences ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                            )
                except Exception as e:
                    logger.warning(f"ensure_schema(user_notification_prefs) warning: {e}")

                # 5) Analytics tables alignment
                try:
                    # popular_searches table with search_count column
                    if not _table_exists('popular_searches'):
                        cursor.execute(
                            """
                            CREATE TABLE IF NOT EXISTS popular_searches (
                              query TEXT PRIMARY KEY,
                              search_count INTEGER NOT NULL DEFAULT 0,
                              last_searched TIMESTAMP NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                    else:
                        # Rename total_count -> search_count if needed
                        if not _column_exists('popular_searches', 'search_count') and _column_exists('popular_searches', 'total_count'):
                            cursor.execute("ALTER TABLE popular_searches RENAME COLUMN total_count TO search_count")
                    # search_history table and execution_time_ms column
                    if not _table_exists('search_history'):
                        cursor.execute(
                            """
                            CREATE TABLE IF NOT EXISTS search_history (
                              id SERIAL PRIMARY KEY,
                              user_id BIGINT,
                              query TEXT NOT NULL,
                              results_count INTEGER NOT NULL DEFAULT 0,
                              execution_time_ms REAL NOT NULL DEFAULT 0,
                              created_at TIMESTAMP NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                    else:
                        if not _column_exists('search_history', 'execution_time_ms'):
                            cursor.execute("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS execution_time_ms REAL DEFAULT 0")
                        if not _column_exists('search_history', 'results_count'):
                            cursor.execute("ALTER TABLE search_history ADD COLUMN IF NOT EXISTS results_count INTEGER DEFAULT 0")
                except Exception as e:
                    logger.warning(f"ensure_schema(analytics) warning: {e}")

                # 5.5) Data health tables (reports & metrics)
                try:
                    # data_health_checks: store individual check results
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS data_health_checks (
                          id SERIAL PRIMARY KEY,
                          check_type TEXT NOT NULL,
                          severity TEXT NOT NULL CHECK (severity IN ('CRITICAL','WARNING','INFO')),
                          category TEXT,
                          issue_count INTEGER NOT NULL DEFAULT 0,
                          details JSONB,
                          check_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                          resolved BOOLEAN NOT NULL DEFAULT FALSE
                        )
                        """
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_health_checks_sev_res ON data_health_checks (severity, resolved)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_health_checks_date ON data_health_checks (check_date DESC)"
                    )

                    # data_quality_metrics: aggregates per check run
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS data_quality_metrics (
                          id SERIAL PRIMARY KEY,
                          metric_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                          total_weapons INTEGER NOT NULL DEFAULT 0,
                          total_attachments INTEGER NOT NULL DEFAULT 0,
                          weapons_with_attachments INTEGER NOT NULL DEFAULT 0,
                          weapons_without_attachments INTEGER NOT NULL DEFAULT 0,
                          attachments_with_images INTEGER NOT NULL DEFAULT 0,
                          attachments_without_images INTEGER NOT NULL DEFAULT 0,
                          health_score REAL NOT NULL DEFAULT 0
                        )
                        """
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_dqm_metric_date ON data_quality_metrics (metric_date DESC)"
                    )
                    # Ensure 'id' column has proper nextval default and sequence ownership (in case of legacy table)
                    def _ensure_serial_default(table: str, seq_name: str):
                        cursor.execute(
                            """
                            SELECT column_default FROM information_schema.columns
                            WHERE table_schema = current_schema() AND table_name = %s AND column_name = 'id'
                            """,
                            (table,),
                        )
                        row = cursor.fetchone()
                        col_default = (row.get('column_default') if row else None)
                        if not col_default or 'nextval' not in str(col_default):
                            # Create sequence and attach to id
                            cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {seq_name}")
                            cursor.execute(f"ALTER SEQUENCE {seq_name} OWNED BY {table}.id")
                            cursor.execute(f"ALTER TABLE {table} ALTER COLUMN id SET DEFAULT nextval('{seq_name}')")

                    _ensure_serial_default('data_quality_metrics', 'data_quality_metrics_id_seq')
                    _ensure_serial_default('data_health_checks', 'data_health_checks_id_seq')
                    # Sync sequences to the current MAX(id) to avoid duplicate key on next inserts
                    try:
                        cursor.execute(
                            """
                            SELECT setval(
                              pg_get_serial_sequence('data_quality_metrics','id'),
                              COALESCE((SELECT MAX(id) FROM data_quality_metrics), 0) + 1,
                              false
                            )
                            """
                        )
                    except Exception as e2:
                        logger.warning(f"ensure_schema(data_quality_metrics setval) warning: {e2}")

                    try:
                        cursor.execute(
                            """
                            SELECT setval(
                              pg_get_serial_sequence('data_health_checks','id'),
                              COALESCE((SELECT MAX(id) FROM data_health_checks), 0) + 1,
                              false
                            )
                            """
                        )
                    except Exception as e3:
                        logger.warning(f"ensure_schema(data_health_checks setval) warning: {e3}")
                except Exception as e:
                    logger.warning(f"ensure_schema(data_health) warning: {e}")

                # 5) ticket_attachments.reply_id (for associating attachments to replies)
                try:
                    if not _column_exists('ticket_attachments', 'reply_id'):
                        cursor.execute(
                            "ALTER TABLE ticket_attachments ADD COLUMN IF NOT EXISTS reply_id INTEGER"
                        )
                        logger.info("Added missing column: ticket_attachments.reply_id")
                    # Optional helpful indexes
                    try:
                        cursor.execute(
                            "CREATE INDEX IF NOT EXISTS ix_ticket_attachments_ticket_id ON ticket_attachments (ticket_id)"
                        )
                        cursor.execute(
                            "CREATE INDEX IF NOT EXISTS ix_ticket_attachments_reply_id ON ticket_attachments (reply_id)"
                        )
                    except Exception as e:
                        logger.warning(f"ensure_schema(ticket_attachments indexes) warning: {e}")
                except Exception as e:
                    logger.warning(f"ensure_schema(ticket_attachments) warning: {e}")
                
                # 6) scheduled_notifications table for recurring broadcasts
                try:
                    # Create table if it does not exist
                    cursor.execute(
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
                        """
                    )
                    # Helpful indexes
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_sched_notif_next_run ON scheduled_notifications (next_run_at)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_sched_notif_enabled_next ON scheduled_notifications (enabled, next_run_at)"
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(scheduled_notifications) warning: {e}")
                
                # 6.5) Attachment analytics tables (metrics, engagement, performance)
                try:
                    # attachment_metrics: event stream of interactions
                    cursor.execute(
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
                        """
                    )
                    # Helpful indexes
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_am_attachment_date ON attachment_metrics (attachment_id, action_date)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_am_action_date ON attachment_metrics (action_type, action_date)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_am_attachment_action ON attachment_metrics (attachment_id, action_type)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_am_user ON attachment_metrics (user_id)"
                    )
                    
                    # user_attachment_engagement: aggregated per user per attachment
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS user_attachment_engagement (
                          user_id BIGINT NOT NULL,
                          attachment_id INTEGER NOT NULL,
                          first_view_date TIMESTAMPTZ,
                          last_view_date TIMESTAMPTZ,
                          total_views INTEGER NOT NULL DEFAULT 0,
                          total_clicks INTEGER NOT NULL DEFAULT 0,
                          rating INTEGER,
                          feedback TEXT,
                          PRIMARY KEY (user_id, attachment_id)
                        )
                        """
                    )
                    # Helpful indexes for analytics
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_uae_attachment ON user_attachment_engagement (attachment_id)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_uae_attachment_rating ON user_attachment_engagement (attachment_id, rating)"
                    )
                    
                    # attachment_performance: daily KPIs per attachment
                    cursor.execute(
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
                        """
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(attachment analytics) warning: {e}")

                # 6.6) CMS tables (content storage with tags and publication state)
                try:
                    cursor.execute(
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
                    )
                    # Helpful indexes
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_cms_content_status_pub ON cms_content (status, published_at DESC)"
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_cms_content_type_status ON cms_content (content_type, status)"
                    )
                    # pg_trgm index for faster title search
                    try:
                        cursor.execute(
                            "CREATE INDEX IF NOT EXISTS ix_cms_content_title_trgm ON cms_content USING gin (title gin_trgm_ops)"
                        )
                    except Exception as e_trgm:
                        logger.warning(f"ensure_schema(cms title trigram index) warning: {e_trgm}")
                    # GIN index on tags JSONB
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_cms_content_tags_gin ON cms_content USING gin (tags)"
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(cms tables) warning: {e}")

                # 7) UA cache tables for dashboards (best-effort)
                try:
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS ua_stats_cache (
                          id INTEGER PRIMARY KEY,
                          total_attachments INTEGER NOT NULL DEFAULT 0,
                          pending_count INTEGER NOT NULL DEFAULT 0,
                          approved_count INTEGER NOT NULL DEFAULT 0,
                          rejected_count INTEGER NOT NULL DEFAULT 0,
                          total_users INTEGER NOT NULL DEFAULT 0,
                          active_users INTEGER NOT NULL DEFAULT 0,
                          banned_users INTEGER NOT NULL DEFAULT 0,
                          br_count INTEGER NOT NULL DEFAULT 0,
                          mp_count INTEGER NOT NULL DEFAULT 0,
                          total_likes INTEGER NOT NULL DEFAULT 0,
                          total_reports INTEGER NOT NULL DEFAULT 0,
                          pending_reports INTEGER NOT NULL DEFAULT 0,
                          last_week_submissions INTEGER NOT NULL DEFAULT 0,
                          last_week_approvals INTEGER NOT NULL DEFAULT 0,
                          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS ua_top_weapons_cache (
                          weapon_name TEXT,
                          attachment_count INTEGER NOT NULL DEFAULT 0,
                          mode TEXT,
                          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_ua_top_weapons_count ON ua_top_weapons_cache (attachment_count DESC)"
                    )
                    cursor.execute(
                        """
                        CREATE TABLE IF NOT EXISTS ua_top_users_cache (
                          user_id BIGINT,
                          username TEXT,
                          approved_count INTEGER NOT NULL DEFAULT 0,
                          total_likes INTEGER NOT NULL DEFAULT 0,
                          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cursor.execute(
                        "CREATE INDEX IF NOT EXISTS ix_ua_top_users_approved ON ua_top_users_cache (approved_count DESC)"
                    )
                except Exception as e:
                    logger.warning(f"ensure_schema(ua cache) warning: {e}")
                # autocommit=True, so no need to commit explicitly
                cursor.close()
                logger.info("Schema guard completed: attachments and ticket_attachments columns verified")
        except Exception as e:
            # Non-fatal: log and continue
            logger.warning(f"Schema guard failed (non-fatal): {e}")
            log_exception(logger, e, "_ensure_schema")

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
