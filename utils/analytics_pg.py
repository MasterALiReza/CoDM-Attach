"""
ماژول مدیریت آمار و تحلیل کانال‌های اجباری - PostgreSQL Backend
این ماژول جایگزین analytics.py می‌شود و از PostgreSQL استفاده می‌کند
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class AnalyticsPostgres:
    """کلاس مدیریت آمار کانال‌ها و کاربران با PostgreSQL Backend"""
    
    def __init__(self, database_url: str = None, db_adapter=None):
        """
        Args:
            database_url: PostgreSQL connection string (اختیاری - از env می‌خواند)
        """
        # Use central DatabaseAdapter (singleton) unless provided
        if db_adapter is None:
            try:
                from core.database.database_adapter import get_database_adapter
                self.db = get_database_adapter()
            except Exception as e:
                raise ValueError(f"Database adapter not available: {e}")
        else:
            self.db = db_adapter

        # Backward-compat: keep attribute but not used directly
        self.database_url = database_url or os.getenv('DATABASE_URL')

        # Ensure schema exists (self-healing) for analytics tables via pooled connection
        try:
            self._ensure_schema()
        except Exception as e:
            logger.warning(f"Could not ensure analytics schema: {e}")
        logger.info("AnalyticsPostgres initialized")
    
    def _get_connection(self):
        """دریافت connection به PostgreSQL"""
        # Delegate to adapter's pooled connection
        return self.db.get_connection()
    
    def _ensure_schema(self) -> None:
        """Ensure required tables for analytics exist."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            # analytics_users
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS analytics_users (
                    user_id BIGINT PRIMARY KEY,
                    first_seen TIMESTAMP NOT NULL DEFAULT NOW(),
                    join_attempts INTEGER NOT NULL DEFAULT 0,
                    completed BOOLEAN NOT NULL DEFAULT FALSE,
                    channels_joined JSONB
                );
                """
            )
            # analytics_channels
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS analytics_channels (
                    channel_id TEXT PRIMARY KEY,
                    title TEXT,
                    url TEXT,
                    added_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    removed_at TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'active',
                    total_joins INTEGER NOT NULL DEFAULT 0,
                    total_join_attempts INTEGER NOT NULL DEFAULT 0,
                    conversion_rate NUMERIC NOT NULL DEFAULT 0,
                    changes JSONB
                );
                """
            )
            # analytics_daily_stats
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS analytics_daily_stats (
                    date DATE PRIMARY KEY,
                    new_users INTEGER NOT NULL DEFAULT 0,
                    successful_joins INTEGER NOT NULL DEFAULT 0,
                    failed_joins INTEGER NOT NULL DEFAULT 0,
                    total_attempts INTEGER NOT NULL DEFAULT 0,
                    conversion_rate NUMERIC NOT NULL DEFAULT 0
                );
                """
            )
            conn.commit()
    
    def _get_today_key(self) -> str:
        """دریافت کلید امروز برای آمار روزانه"""
        return datetime.now().strftime("%Y-%m-%d")
    
    def _ensure_daily_stats(self, cursor, date_key: str):
        """اطمینان از وجود ساختار آمار روزانه"""
        cursor.execute("""
            INSERT INTO analytics_daily_stats (date)
            VALUES (%s)
            ON CONFLICT (date) DO NOTHING
        """, (date_key,))
    
    # ===== User Tracking =====
    
    def track_user_start(self, user_id: int) -> bool:
        """ثبت اولین ورود کاربر به ربات"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # اگر کاربر جدید است
                cursor.execute("""
                    INSERT INTO analytics_users (user_id, first_seen)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                    RETURNING user_id
                """, (user_id, datetime.now()))
                
                is_new = cursor.fetchone() is not None
                
                if is_new:
                    # آمار روزانه
                    today = self._get_today_key()
                    self._ensure_daily_stats(cursor, today)
                    cursor.execute("""
                        UPDATE analytics_daily_stats
                        SET new_users = new_users + 1
                        WHERE date = %s
                    """, (today,))
                    
                    logger.info(f"[Analytics] New user tracked: {user_id}")
                
                conn.commit()
                cursor.close()
                return True
                
        except Exception as e:
            logger.error(f"[Analytics] Error tracking user start: {e}")
            return False
    
    def track_join_attempt(self, user_id: int, channel_id: str) -> bool:
        """ثبت تلاش برای عضویت (زدن دکمه عضو شدم)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # اطمینان از وجود کاربر
                cursor.execute("""
                    INSERT INTO analytics_users (user_id, first_seen)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, datetime.now()))
                
                # افزایش تعداد تلاش‌ها
                cursor.execute("""
                    UPDATE analytics_users
                    SET join_attempts = join_attempts + 1,
                        channels_joined = jsonb_set(
                            COALESCE(channels_joined, '{}'::jsonb),
                            ARRAY[%s],
                            jsonb_build_object(
                                'joined_at', NULL,
                                'attempts', COALESCE((channels_joined->%s->>'attempts')::int, 0) + 1
                            ),
                            true
                        )
                    WHERE user_id = %s
                """, (channel_id, channel_id, user_id))
                
                # آمار کانال
                cursor.execute("""
                    UPDATE analytics_channels
                    SET total_join_attempts = total_join_attempts + 1
                    WHERE channel_id = %s
                """, (channel_id,))
                
                # آمار روزانه
                today = self._get_today_key()
                self._ensure_daily_stats(cursor, today)
                cursor.execute("""
                    UPDATE analytics_daily_stats
                    SET total_attempts = total_attempts + 1
                    WHERE date = %s
                """, (today,))
                
                conn.commit()
                cursor.close()
                logger.info(f"[Analytics] Join attempt: user={user_id}, channel={channel_id}")
                return True
                
        except Exception as e:
            logger.error(f"[Analytics] Error tracking join attempt: {e}")
            return False
    
    def track_join_success(self, user_id: int, channel_id: str) -> bool:
        """ثبت عضویت موفق در کانال"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # اطمینان از وجود کاربر
                cursor.execute("""
                    INSERT INTO analytics_users (user_id, first_seen)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, datetime.now()))
                
                # ثبت زمان عضویت موفق
                cursor.execute("""
                    UPDATE analytics_users
                    SET channels_joined = jsonb_set(
                        COALESCE(channels_joined, '{}'::jsonb),
                        ARRAY[%s, 'joined_at'],
                        to_jsonb(%s::text),
                        true
                    )
                    WHERE user_id = %s
                """, (channel_id, datetime.now().isoformat(), user_id))
                
                # چک کردن completion (همه کانال‌های فعال را join کرده؟)
                cursor.execute("""
                    SELECT COUNT(*) as active_count
                    FROM analytics_channels
                    WHERE status = 'active'
                """)
                _row = cursor.fetchone()
                active_count = int((_row or {}).get('active_count') or 0)
                
                cursor.execute("""
                    SELECT jsonb_object_keys(channels_joined) as channel_id
                    FROM analytics_users
                    WHERE user_id = %s
                """, (user_id,))
                joined_channels = [row['channel_id'] for row in cursor.fetchall()]
                
                # بررسی تعداد کانال‌های active که join شده
                cursor.execute("""
                    SELECT COUNT(*) as joined_active
                    FROM analytics_channels
                    WHERE status = 'active' 
                    AND channel_id = ANY(%s)
                """, (joined_channels,))
                _row2 = cursor.fetchone()
                joined_active_count = int((_row2 or {}).get('joined_active') or 0)
                
                if joined_active_count >= active_count and active_count > 0:
                    cursor.execute("""
                        UPDATE analytics_users
                        SET completed = TRUE
                        WHERE user_id = %s
                    """, (user_id,))
                
                # آمار کانال
                cursor.execute("""
                    UPDATE analytics_channels
                    SET total_joins = total_joins + 1,
                        conversion_rate = CASE 
                            WHEN total_join_attempts > 0 
                            THEN ROUND(((total_joins + 1)::numeric / total_join_attempts::numeric) * 100, 2)
                            ELSE 0.0
                        END
                    WHERE channel_id = %s
                """, (channel_id,))
                
                # آمار روزانه
                today = self._get_today_key()
                self._ensure_daily_stats(cursor, today)
                cursor.execute("""
                    UPDATE analytics_daily_stats
                    SET successful_joins = successful_joins + 1,
                        conversion_rate = CASE
                            WHEN total_attempts > 0
                            THEN ROUND(((successful_joins + 1)::numeric / total_attempts::numeric) * 100, 2)
                            ELSE 0.0
                        END
                    WHERE date = %s
                """, (today,))
                
                conn.commit()
                cursor.close()
                logger.info(f"[Analytics] Join success: user={user_id}, channel={channel_id}")
                return True
                
        except Exception as e:
            logger.error(f"[Analytics] Error tracking join success: {e}")
            return False
    
    # ===== Channel Management Tracking =====
    
    def track_channel_added(self, channel_id: str, title: str, url: str, admin_id: int) -> bool:
        """ثبت افزودن کانال جدید"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                changes = [{
                    "timestamp": datetime.now().isoformat(),
                    "action": "added",
                    "admin_id": admin_id
                }]
                
                cursor.execute("""
                    INSERT INTO analytics_channels 
                    (channel_id, title, url, added_at, status, changes)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        url = EXCLUDED.url,
                        status = 'active'
                """, (channel_id, title, url, datetime.now(), 'active', json.dumps(changes)))
                
                conn.commit()
                cursor.close()
                logger.info(f"[Analytics] Channel added: {channel_id} by admin {admin_id}")
                return True
                
        except Exception as e:
            logger.error(f"[Analytics] Error tracking channel added: {e}")
            return False
    
    def track_channel_removed(self, channel_id: str, admin_id: int) -> bool:
        """ثبت حذف کانال"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    UPDATE analytics_channels
                    SET removed_at = %s,
                        status = 'removed',
                        changes = changes || %s::jsonb
                    WHERE channel_id = %s
                """, (
                    datetime.now(),
                    json.dumps([{
                        "timestamp": datetime.now().isoformat(),
                        "action": "removed",
                        "admin_id": admin_id
                    }]),
                    channel_id
                ))
                
                conn.commit()
                cursor.close()
                logger.info(f"[Analytics] Channel removed: {channel_id} by admin {admin_id}")
                return True
                
        except Exception as e:
            logger.error(f"[Analytics] Error tracking channel removed: {e}")
            return False
    
    def track_channel_updated(self, channel_id: str, admin_id: int, 
                             title: str = None, url: str = None) -> bool:
        """ثبت ویرایش کانال"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                changes_list = []
                update_fields = []
                params = []
                
                if title:
                    update_fields.append("title = %s")
                    params.append(title)
                    changes_list.append(f"title: {title}")
                
                if url:
                    update_fields.append("url = %s")
                    params.append(url)
                    changes_list.append(f"url: {url}")
                
                if changes_list:
                    change_entry = {
                        "timestamp": datetime.now().isoformat(),
                        "action": "updated",
                        "admin_id": admin_id,
                        "changes": ", ".join(changes_list)
                    }
                    
                    update_fields.append("changes = changes || %s::jsonb")
                    params.append(json.dumps([change_entry]))
                    params.append(channel_id)
                    
                    query = f"UPDATE analytics_channels SET {', '.join(update_fields)} WHERE channel_id = %s"
                    cursor.execute(query, params)
                    
                    conn.commit()
                    logger.info(f"[Analytics] Channel updated: {channel_id} by admin {admin_id}")
                
                cursor.close()
                return True
                
        except Exception as e:
            logger.error(f"[Analytics] Error tracking channel updated: {e}")
            return False
    
    # ===== Get Statistics =====
    
    def get_channel_stats(self, channel_id: str) -> Optional[Dict]:
        """دریافت آمار یک کانال"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM analytics_channels WHERE channel_id = %s
                """, (channel_id,))
                
                row = cursor.fetchone()
                cursor.close()
                
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"[Analytics] Error getting channel stats: {e}")
            return None
    
    def get_all_channels_stats(self) -> List[Dict]:
        """دریافت آمار همه کانال‌ها"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM analytics_channels ORDER BY added_at DESC")
                
                rows = cursor.fetchall()
                cursor.close()
                
                return [dict(r) for r in rows]
                
        except Exception as e:
            logger.error(f"[Analytics] Error getting all channels: {e}")
            return []
    
    def get_active_channels_stats(self) -> List[Dict]:
        """دریافت آمار کانال‌های فعال"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM analytics_channels 
                    WHERE status = 'active' 
                    ORDER BY added_at DESC
                """)
                
                rows = cursor.fetchall()
                cursor.close()
                
                return [dict(r) for r in rows]
                
        except Exception as e:
            logger.error(f"[Analytics] Error getting active channels: {e}")
            return []
    
    def get_removed_channels_stats(self) -> List[Dict]:
        """دریافت آمار کانال‌های حذف شده"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM analytics_channels 
                    WHERE status = 'removed' 
                    ORDER BY removed_at DESC
                """)
                
                rows = cursor.fetchall()
                cursor.close()
                
                return [dict(r) for r in rows]
                
        except Exception as e:
            logger.error(f"[Analytics] Error getting removed channels: {e}")
            return []
    
    def get_daily_stats(self, date_key: str = None) -> Dict:
        """دریافت آمار روزانه"""
        if date_key is None:
            date_key = self._get_today_key()
        
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                self._ensure_daily_stats(cursor, date_key)
                
                cursor.execute("""
                    SELECT * FROM analytics_daily_stats WHERE date = %s
                """, (date_key,))
                
                row = cursor.fetchone()
                conn.commit()
                cursor.close()
                
                if row:
                    return dict(row)
                return {}
                
        except Exception as e:
            logger.error(f"[Analytics] Error getting daily stats: {e}")
            return {}
    
    def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """دریافت آمار یک کاربر"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT * FROM analytics_users WHERE user_id = %s
                """, (user_id,))
                
                row = cursor.fetchone()
                cursor.close()
                
                if row:
                    result = dict(row)
                    # تبدیل JSONB به dict
                    if 'channels_joined' in result and result['channels_joined']:
                        result['channels_joined'] = json.loads(result['channels_joined']) if isinstance(result['channels_joined'], str) else result['channels_joined']
                    return result
                return None
                
        except Exception as e:
            logger.error(f"[Analytics] Error getting user stats: {e}")
            return None
    
    def get_total_users(self) -> int:
        """دریافت تعداد کل کاربران"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) AS count FROM analytics_users")
                row = cursor.fetchone()
                count = int(row.get('count') or 0) if row else 0
                cursor.close()
                return count
        except Exception as e:
            logger.error(f"[Analytics] Error getting total users: {e}")
            return 0
    
    def get_completed_users(self) -> int:
        """دریافت تعداد کاربرانی که همه کانال‌ها را join کردند"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) AS count FROM analytics_users WHERE completed = TRUE")
                row = cursor.fetchone()
                count = int(row.get('count') or 0) if row else 0
                cursor.close()
                return count
        except Exception as e:
            logger.error(f"[Analytics] Error getting completed users: {e}")
            return 0
    
    # ===== Dashboard Generation =====
    
    def generate_admin_dashboard(self) -> str:
        """ایجاد dashboard متنی برای ادمین"""
        try:
            lines = []
            lines.append("📊 <b>آمار کانال‌های اجباری</b>\n")
            
            # آمار کلی
            total_users = self.get_total_users()
            completed_users = self.get_completed_users()
            
            lines.append(f"👥 کل کاربران: <b>{total_users}</b>")
            if total_users > 0:
                completion_rate = round((completed_users / total_users) * 100, 1)
                lines.append(f"✅ تکمیل شده: <b>{completed_users}</b> ({completion_rate}%)")
                lines.append(f"❌ ناتمام: <b>{total_users - completed_users}</b>\n")
            else:
                lines.append("✅ تکمیل شده: <b>0</b>")
                lines.append("❌ ناتمام: <b>0</b>\n")
            
            # آمار کانال‌های فعال
            active_channels = self.get_active_channels_stats()
            removed_channels = self.get_removed_channels_stats()
            
            lines.append(f"🟢 کانال‌های فعال: <b>{len(active_channels)}</b>")
            lines.append(f"🔴 کانال‌های حذف شده: <b>{len(removed_channels)}</b>\n")
            
            # جزئیات هر کانال فعال
            if active_channels:
                lines.append("📢 <b>کانال‌های فعال:</b>\n")
                for i, channel in enumerate(active_channels[:5], 1):  # فقط 5 تا اول
                    title = channel.get("title", "Unknown")
                    joins = channel.get("total_joins", 0)
                    attempts = channel.get("total_join_attempts", 0)
                    conv_rate = channel.get("conversion_rate", 0.0)
                    
                    lines.append(f"{i}. <b>{title}</b>")
                    lines.append(f"   • عضو شده: {joins} نفر")
                    lines.append(f"   • تلاش: {attempts} بار")
                    lines.append(f"   • نرخ تبدیل: {conv_rate}%\n")
            
            # آمار امروز
            today_stats = self.get_daily_stats()
            if today_stats.get("new_users", 0) > 0 or today_stats.get("successful_joins", 0) > 0:
                lines.append("📅 <b>آمار امروز:</b>")
                lines.append(f"   • کاربران جدید: {today_stats.get('new_users', 0)}")
                lines.append(f"   • عضویت موفق: {today_stats.get('successful_joins', 0)}")
                lines.append(f"   • نرخ تبدیل: {today_stats.get('conversion_rate', 0)}%")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"[Analytics] Error generating dashboard: {e}")
            return "❌ خطا در ایجاد dashboard"
    
    def generate_channel_history_report(self) -> str:
        """ایجاد گزارش تاریخچه کانال‌های حذف شده (PostgreSQL)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT title, total_joins, added_at, removed_at
                    FROM analytics_channels
                    WHERE status = 'removed'
                    ORDER BY removed_at DESC NULLS LAST
                    """
                )
                rows = cursor.fetchall()
                cursor.close()
                removed_channels = [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"[Analytics] Error generating history report: {e}")
            removed_channels = []

        if not removed_channels:
            return "📋 <b>تاریخچه کانال‌های حذف شده</b>\n\nهیچ کانال حذف شده‌ای وجود ندارد."

        lines = []
        lines.append("📋 <b>تاریخچه کانال‌های حذف شده</b>\n")
        for i, ch in enumerate(removed_channels, 1):
            title = ch.get("title", "Unknown")
            joins = ch.get("total_joins", 0)
            added_at = ch.get("added_at")
            removed_at = ch.get("removed_at")
            # محاسبه مدت فعالیت
            try:
                from datetime import datetime as _dt
                if added_at and removed_at:
                    if not isinstance(added_at, _dt):
                        added_at = _dt.fromisoformat(str(added_at))
                    if not isinstance(removed_at, _dt):
                        removed_at = _dt.fromisoformat(str(removed_at))
                    duration_days = (removed_at - added_at).days
                    duration_str = f"{duration_days} روز"
                else:
                    duration_str = "نامشخص"
            except Exception:
                duration_str = "نامشخص"

            lines.append(f"{i}. <b>{title}</b>")
            lines.append(f"   • کل اعضا: {joins} نفر")
            lines.append(f"   • مدت فعالیت: {duration_str}")
            lines.append(
                f"   • حذف شده: {str(removed_at)[:10] if removed_at else 'نامشخص'}\n"
            )

        return "\n".join(lines)

    def generate_funnel_analysis(self) -> str:
        """تحلیل قیف تبدیل کاربران (PostgreSQL)"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) AS count FROM analytics_users")
                row = cursor.fetchone(); started = int(row.get('count') or 0) if row else 0
                cursor.execute("SELECT COUNT(*) AS count FROM analytics_users WHERE join_attempts > 0")
                row = cursor.fetchone(); attempted = int(row.get('count') or 0) if row else 0
                cursor.execute("SELECT COUNT(*) AS count FROM analytics_users WHERE completed = TRUE")
                row = cursor.fetchone(); completed = int(row.get('count') or 0) if row else 0
                cursor.close()
        except Exception as e:
            logger.error(f"[Analytics] Error generating funnel: {e}")
            started = attempted = completed = 0

        if started == 0:
            return "📈 <b>تحلیل قیف تبدیل</b>\n\nهنوز کاربری ثبت نشده است."

        lines = []
        lines.append("📈 <b>تحلیل قیف تبدیل کاربران</b>\n")
        lines.append(f"1️⃣ کاربران جدید (شروع /start): <b>{started}</b> نفر")
        lines.append("        ↓")
        drop_1 = max(0, started - attempted)
        drop_1_pct = round((drop_1 / started) * 100, 1) if started > 0 else 0
        lines.append(f"2️⃣ تلاش برای عضویت: <b>{attempted}</b> نفر (-{drop_1_pct}%)")
        if attempted > 0:
            lines.append("        ↓")
            drop_2 = max(0, attempted - completed)
            drop_2_pct = round((drop_2 / attempted) * 100, 1) if attempted > 0 else 0
            lines.append(f"3️⃣ عضویت تایید شد: <b>{completed}</b> نفر (-{drop_2_pct}%)\n")
            conversion = round((completed / started) * 100, 1)
            lines.append(f"✅ <b>نرخ تبدیل کلی:</b> {conversion}%")
            lines.append(f"❌ <b>نرخ ریزش کلی:</b> {100 - conversion}%")

        return "\n".join(lines)

    def export_to_csv(self, export_type: str = "all") -> list:
        """Export آمار به CSV: channels | users | daily | all. برمی‌گرداند مسیر فایل‌ها."""
        files_created = []
        try:
            import csv, os
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_dir = "exports"
            os.makedirs(export_dir, exist_ok=True)

            with self._get_connection() as conn:
                cursor = conn.cursor()

                if export_type in ("channels", "all"):
                    cursor.execute(
                        "SELECT channel_id, title, url, status, total_joins, total_join_attempts, conversion_rate, added_at, removed_at FROM analytics_channels ORDER BY added_at DESC"
                    )
                    rows = cursor.fetchall()
                    filename = os.path.join(export_dir, f"channels_{ts}.csv")
                    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            "Channel ID", "Title", "URL", "Status", "Total Joins",
                            "Total Attempts", "Conversion Rate", "Added At", "Removed At"
                        ])
                        for r in rows:
                            writer.writerow([
                                r['channel_id'], r['title'], r['url'], r['status'],
                                r['total_joins'], r['total_join_attempts'], r['conversion_rate'],
                                r['added_at'], r['removed_at']
                            ])
                    files_created.append(filename)

                if export_type in ("users", "all"):
                    cursor.execute(
                        "SELECT user_id, first_seen, completed, join_attempts FROM analytics_users ORDER BY first_seen DESC"
                    )
                    rows = cursor.fetchall()
                    filename = os.path.join(export_dir, f"users_{ts}.csv")
                    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        writer.writerow(["User ID", "First Seen", "Completed", "Join Attempts"])
                        for r in rows:
                            writer.writerow([r['user_id'], r['first_seen'], r['completed'], r['join_attempts']])
                    files_created.append(filename)

                if export_type in ("daily", "all"):
                    cursor.execute(
                        "SELECT date, new_users, successful_joins, failed_joins, total_attempts, conversion_rate FROM analytics_daily_stats ORDER BY date DESC"
                    )
                    rows = cursor.fetchall()
                    filename = os.path.join(export_dir, f"daily_stats_{ts}.csv")
                    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
                        writer = csv.writer(f)
                        writer.writerow([
                            "Date", "New Users", "Successful Joins", "Failed Joins", "Total Attempts", "Conversion Rate"
                        ])
                        for r in rows:
                            writer.writerow([
                                r['date'], r['new_users'], r['successful_joins'], r['failed_joins'], r['total_attempts'], r['conversion_rate']
                            ])
                    files_created.append(filename)

                cursor.close()

        except Exception as e:
            logger.error(f"[Analytics] Error exporting to CSV: {e}")
            return []

        return files_created

    def generate_period_report(self, start_date: str = None, end_date: str = None) -> str:
        """ایجاد گزارش دوره‌ای مبتنی بر جدول analytics_daily_stats"""
        try:
            from datetime import datetime as _dt, timedelta as _td
            if not end_date:
                end_date = _dt.now().strftime("%Y-%m-%d")
            if not start_date:
                start_date = (_dt.now() - _td(days=7)).strftime("%Y-%m-%d")

            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 
                        COALESCE(SUM(new_users),0) AS total_new_users, 
                        COALESCE(SUM(successful_joins),0) AS total_successful, 
                        COALESCE(SUM(total_attempts),0) AS total_attempts, 
                        COUNT(*) AS days_with_data
                    FROM analytics_daily_stats
                    WHERE date BETWEEN %s AND %s
                    """,
                    (start_date, end_date)
                )
                row = cursor.fetchone()
                cursor.close()

            total_new_users = int(row.get('total_new_users') or 0) if row else 0
            total_successful = int(row.get('total_successful') or 0) if row else 0
            total_attempts = int(row.get('total_attempts') or 0) if row else 0
            days_with_data = int(row.get('days_with_data') or 0) if row else 0
            lines = []
            lines.append("📊 <b>گزارش دوره‌ای</b>")
            lines.append(f"📅 از {start_date} تا {end_date}\n")

            if days_with_data == 0:
                lines.append("⚠️ هیچ داده‌ای در این بازه زمانی وجود ندارد.")
                return "\n".join(lines)

            lines.append(f"👥 <b>کاربران جدید:</b> {total_new_users} نفر")
            lines.append(f"✅ <b>عضویت موفق:</b> {total_successful} نفر")
            lines.append(f"🔄 <b>کل تلاش‌ها:</b> {total_attempts} بار")

            avg_users = round(total_new_users / days_with_data, 1)
            avg_success = round(total_successful / days_with_data, 1)
            lines.append("\n📈 <b>میانگین روزانه:</b>")
            lines.append(f"   • کاربران جدید: {avg_users} نفر")
            lines.append(f"   • عضویت موفق: {avg_success} نفر")

            if total_attempts > 0:
                period_conv = round((total_successful / total_attempts) * 100, 1)
                lines.append(f"\n✅ <b>نرخ تبدیل دوره:</b> {period_conv}%")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"[Analytics] Error generating period report: {e}")
            return "❌ خطا در ایجاد گزارش دوره‌ای"
