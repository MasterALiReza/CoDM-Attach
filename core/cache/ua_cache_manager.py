"""
User Attachments Cache Manager
مدیریت Cache برای بهبود Performance سیستم اتچمنت کاربران
"""

import time
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from functools import wraps
from threading import Lock
from utils.logger import get_logger

logger = get_logger('ua_cache', 'cache.log')


class UACache:
    """مدیریت Cache برای User Attachments"""
    
    def __init__(self, db_adapter, ttl_seconds: int = 300):
        """
        Args:
            db_adapter: Database adapter instance
            ttl_seconds: Time to live for cache entries (default: 5 minutes)
        """
        self.db = db_adapter
        self.ttl = ttl_seconds
        self.memory_cache = {}
        self.lock = Lock()
        
    def _is_cache_valid(self, updated_at: str) -> bool:
        """بررسی اعتبار cache بر اساس زمان"""
        if not updated_at:
            return False
            
        try:
            cache_time = datetime.fromisoformat(updated_at)
            expiry_time = datetime.now() - timedelta(seconds=self.ttl)
            return cache_time > expiry_time
        except Exception as e:
            logger.error(f"Error checking cache validity: {e}")
            return False
    
    def get_stats(self, force_refresh: bool = False) -> Optional[Dict]:
        """دریافت آمار از cache یا محاسبه جدید"""
        
        # بررسی memory cache اول
        if not force_refresh and 'stats' in self.memory_cache:
            cached = self.memory_cache['stats']
            if self._is_cache_valid(cached.get('timestamp')):
                logger.debug("Stats retrieved from memory cache")
                return cached['data']
        
        try:
            if not hasattr(self.db, 'get_connection'):
                return None
            
            # بررسی database cache
            cache_row = None
            if not force_refresh:
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        try:
                            cursor.execute(
                                """
                                SELECT * FROM ua_stats_cache 
                                WHERE id = 1 
                                  AND updated_at > (CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                                """
                            )
                        except Exception as e:
                            logger.debug(f"Cache table might not have updated_at column or table missing: {e}")
                            cursor.execute(
                                """
                                SELECT * FROM ua_stats_cache 
                                WHERE id = 1
                                """
                            )
                        cache_row = cursor.fetchone()
                except Exception as cache_err:
                    logger.debug(f"Skipping DB cache for stats (will compute fresh): {cache_err}")
                    cache_row = None
                
                if cache_row:
                    stats = dict(cache_row)
                    with self.lock:
                        self.memory_cache['stats'] = {
                            'data': stats,
                            'timestamp': datetime.now().isoformat()
                        }
                    logger.debug("Stats retrieved from database cache")
                    return stats
            
            # محاسبه آمار جدید با CTE
            logger.info("Calculating fresh stats with CTE")
            start_time = time.time()
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    WITH stats AS (
                        SELECT 
                            COUNT(*) as total_attachments,
                            COUNT(CASE WHEN status = 'pending' THEN 1 END) as pending_count,
                            COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
                            COUNT(CASE WHEN status = 'rejected' THEN 1 END) as rejected_count,
                            COUNT(CASE WHEN mode = 'br' AND status = 'approved' THEN 1 END) as br_count,
                            COUNT(CASE WHEN mode = 'mp' AND status = 'approved' THEN 1 END) as mp_count,
                            COUNT(DISTINCT user_id) as total_users,
                            COALESCE(SUM(like_count), 0) as total_likes,
                            COALESCE(SUM(report_count), 0) as total_reports,
                            COUNT(CASE WHEN submitted_at >= (CURRENT_TIMESTAMP - INTERVAL '7 days') THEN 1 END) as last_week_submissions,
                            COUNT(CASE WHEN approved_at >= (CURRENT_TIMESTAMP - INTERVAL '7 days') AND status = 'approved' THEN 1 END) as last_week_approvals
                        FROM user_attachments
                    ),
                    banned AS (
                        SELECT COUNT(*) as banned_users
                        FROM user_submission_stats 
                        WHERE is_banned = TRUE
                    ),
                    reports AS (
                        SELECT COUNT(*) as pending_reports
                        FROM user_attachment_reports
                        WHERE status = 'pending'
                    )
                    SELECT 
                        s.*,
                        b.banned_users,
                        r.pending_reports,
                        s.total_users - b.banned_users as active_users
                    FROM stats s, banned b, reports r
                    """
                )
                row = cursor.fetchone()
            elapsed = (time.time() - start_time) * 1000
            logger.info(f"Stats calculated in {elapsed:.2f}ms")
            
            if row:
                stats = dict(row)
                stats['updated_at'] = datetime.now().isoformat()
                
                # ذخیره در database cache
                try:
                    with self.db.transaction() as tconn:
                        tcur = tconn.cursor()
                        tcur.execute(
                            """
                            INSERT INTO ua_stats_cache (
                                id, total_attachments, pending_count, approved_count, rejected_count,
                                total_users, active_users, banned_users, br_count, mp_count,
                                total_likes, total_reports, pending_reports,
                                last_week_submissions, last_week_approvals,
                                updated_at
                            ) VALUES (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (id) DO UPDATE SET
                                total_attachments = EXCLUDED.total_attachments,
                                pending_count = EXCLUDED.pending_count,
                                approved_count = EXCLUDED.approved_count,
                                rejected_count = EXCLUDED.rejected_count,
                                total_users = EXCLUDED.total_users,
                                active_users = EXCLUDED.active_users,
                                banned_users = EXCLUDED.banned_users,
                                br_count = EXCLUDED.br_count,
                                mp_count = EXCLUDED.mp_count,
                                total_likes = EXCLUDED.total_likes,
                                total_reports = EXCLUDED.total_reports,
                                pending_reports = EXCLUDED.pending_reports,
                                last_week_submissions = EXCLUDED.last_week_submissions,
                                last_week_approvals = EXCLUDED.last_week_approvals,
                                updated_at = CURRENT_TIMESTAMP
                            """,
                            (
                                stats['total_attachments'], stats['pending_count'], stats['approved_count'],
                                stats['rejected_count'], stats['total_users'], stats['active_users'],
                                stats['banned_users'], stats['br_count'], stats['mp_count'],
                                stats['total_likes'], stats['total_reports'], stats['pending_reports'],
                                stats['last_week_submissions'], stats['last_week_approvals']
                            ),
                        )
                except Exception as e:
                    logger.debug(f"Could not update cache table: {e}")
                
                # ذخیره در memory cache
                with self.lock:
                    self.memory_cache['stats'] = {
                        'data': stats,
                        'timestamp': datetime.now().isoformat()
                    }
                
                return stats
                
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return None
    
    def get_top_weapons(self, limit: int = 10, force_refresh: bool = False) -> List[Dict]:
        """دریافت محبوب‌ترین سلاح‌ها از cache"""
        
        try:
            limit = int(limit)
        except Exception:
            limit = 10
        limit = max(1, min(limit, 100))
        cache_key = f'top_weapons_{limit}'
        
        # بررسی memory cache
        if not force_refresh and cache_key in self.memory_cache:
            cached = self.memory_cache[cache_key]
            if self._is_cache_valid(cached.get('timestamp')):
                logger.debug(f"Top weapons retrieved from memory cache")
                return cached['data']
        
        try:
            if not hasattr(self.db, 'get_connection'):
                return []
            
            # بررسی database cache
            if not force_refresh:
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        try:
                            cursor.execute(
                                """
                                SELECT weapon_name, attachment_count, mode
                                FROM ua_top_weapons_cache
                                WHERE updated_at > (CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                                ORDER BY attachment_count DESC
                                LIMIT %s
                                """,
                                (limit,),
                            )
                        except Exception:
                            cursor.execute(
                                """
                                SELECT weapon_name, attachment_count, mode
                                FROM ua_top_weapons_cache
                                ORDER BY attachment_count DESC
                                LIMIT %s
                                """,
                                (limit,),
                            )
                        cache_rows = cursor.fetchall()
                    if cache_rows:
                        weapons = [dict(row) for row in cache_rows]
                        with self.lock:
                            self.memory_cache[cache_key] = {
                                'data': weapons,
                                'timestamp': datetime.now().isoformat()
                            }
                        logger.debug("Top weapons retrieved from database cache")
                        return weapons
                except Exception as cache_err:
                    logger.debug(f"Skipping DB cache for top weapons: {cache_err}")
            
            # محاسبه جدید
            logger.info("Calculating fresh top weapons")
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 
                        COALESCE(custom_weapon_name, 'Unknown') as weapon_name,
                        COUNT(*) as attachment_count,
                        mode
                    FROM user_attachments
                    WHERE status = 'approved' 
                      AND custom_weapon_name IS NOT NULL
                    GROUP BY custom_weapon_name, mode
                    ORDER BY attachment_count DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
            weapons = [dict(row) for row in rows]
            
            # ذخیره در database cache
            try:
                with self.db.transaction() as tconn:
                    tcur = tconn.cursor()
                    tcur.execute("DELETE FROM ua_top_weapons_cache")
                    for weapon in weapons:
                        tcur.execute(
                            """
                            INSERT INTO ua_top_weapons_cache (weapon_name, attachment_count, mode, updated_at)
                            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                            """,
                            (weapon['weapon_name'], weapon['attachment_count'], weapon.get('mode', '')),
                        )
            except Exception as e:
                logger.debug(f"Could not refresh top weapons cache: {e}")
            
            # ذخیره در memory cache
            with self.lock:
                self.memory_cache[cache_key] = {
                    'data': weapons,
                    'timestamp': datetime.now().isoformat()
                }
            
            return weapons
            
        except Exception as e:
            logger.error(f"Error getting top weapons: {e}")
            return []
    
    def get_top_users(self, limit: int = 5, force_refresh: bool = False) -> List[Dict]:
        """دریافت فعال‌ترین کاربران از cache"""
        
        try:
            limit = int(limit)
        except Exception:
            limit = 5
        limit = max(1, min(limit, 100))
        cache_key = f'top_users_{limit}'
        
        # بررسی memory cache
        if not force_refresh and cache_key in self.memory_cache:
            cached = self.memory_cache[cache_key]
            if self._is_cache_valid(cached.get('timestamp')):
                logger.debug("Top users retrieved from memory cache")
                return cached['data']
        
        try:
            if not hasattr(self.db, 'get_connection'):
                return []
            
            # بررسی database cache
            if not force_refresh:
                try:
                    with self.db.get_connection() as conn:
                        cursor = conn.cursor()
                        try:
                            cursor.execute(
                                """
                                SELECT user_id, username, approved_count, total_likes
                                FROM ua_top_users_cache
                                WHERE updated_at > (CURRENT_TIMESTAMP - INTERVAL '5 minutes')
                                ORDER BY approved_count DESC
                                LIMIT %s
                                """,
                                (limit,),
                            )
                        except Exception:
                            cursor.execute(
                                """
                                SELECT user_id, username, approved_count, total_likes
                                FROM ua_top_users_cache
                                ORDER BY approved_count DESC
                                LIMIT %s
                                """,
                                (limit,),
                            )
                        cache_rows = cursor.fetchall()
                    if cache_rows:
                        users = [dict(row) for row in cache_rows]
                        with self.lock:
                            self.memory_cache[cache_key] = {
                                'data': users,
                                'timestamp': datetime.now().isoformat()
                            }
                        logger.debug("Top users retrieved from database cache")
                        return users
                except Exception as cache_err:
                    logger.debug(f"Skipping DB cache for top users: {cache_err}")
            
            # محاسبه جدید
            logger.info("Calculating fresh top users")
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT 
                        ua.user_id,
                        u.username,
                        COUNT(*) as approved_count,
                        COALESCE(SUM(ua.like_count), 0) as total_likes
                    FROM user_attachments ua
                    LEFT JOIN users u ON ua.user_id = u.user_id
                    WHERE ua.status = 'approved'
                    GROUP BY ua.user_id, u.username
                    ORDER BY approved_count DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
            users = [dict(row) for row in rows]
            
            # ذخیره در database cache
            try:
                with self.db.transaction() as tconn:
                    tcur = tconn.cursor()
                    tcur.execute("DELETE FROM ua_top_users_cache")
                    for user in users:
                        tcur.execute(
                            """
                            INSERT INTO ua_top_users_cache (user_id, username, approved_count, total_likes, updated_at)
                            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                            """,
                            (user['user_id'], user.get('username'), user['approved_count'], user['total_likes']),
                        )
            except Exception as e:
                logger.debug(f"Could not refresh top users cache: {e}")
            
            # ذخیره در memory cache
            with self.lock:
                self.memory_cache[cache_key] = {
                    'data': users,
                    'timestamp': datetime.now().isoformat()
                }
            
            return users
            
        except Exception as e:
            logger.error(f"Error getting top users: {e}")
            return []
    
    def get_paginated_count(self, status: str = 'pending') -> int:
        """دریافت تعداد برای pagination با cache"""
        
        cache_key = f'count_{status}'
        
        # بررسی memory cache (کوتاه‌تر برای counts)
        if cache_key in self.memory_cache:
            cached = self.memory_cache[cache_key]
            cache_time = cached.get('timestamp', 0)
            if time.time() - cache_time < 60:  # 1 minute cache for counts
                logger.debug(f"Count for {status} from memory cache")
                return cached['count']
        
        try:
            if not hasattr(self.db, 'get_connection'):
                return 0
            
            # استفاده از stats cache اگر موجود باشه
            if status in ['pending', 'approved', 'rejected']:
                stats = self.get_stats()
                if stats:
                    count = stats.get(f'{status}_count', 0)
                    with self.lock:
                        self.memory_cache[cache_key] = {
                            'count': count,
                            'timestamp': time.time()
                        }
                    return count
            
            # Query مستقیم اگر cache موجود نباشه
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM user_attachments WHERE status = %s",
                    (status,),
                )
                row = cursor.fetchone()
                count = int((row or {}).get('cnt') or 0)
            
            # ذخیره در memory cache
            with self.lock:
                self.memory_cache[cache_key] = {
                    'count': count,
                    'timestamp': time.time()
                }
            
            return count
            
        except Exception as e:
            logger.error(f"Error getting count for {status}: {e}")
            return 0
    
    def invalidate(self, cache_type: Optional[str] = None):
        """پاک کردن cache"""
        
        with self.lock:
            if cache_type:
                # پاک کردن نوع خاصی از cache
                keys_to_delete = [k for k in self.memory_cache if k.startswith(cache_type)]
                for key in keys_to_delete:
                    del self.memory_cache[key]
                logger.info(f"Invalidated {len(keys_to_delete)} {cache_type} cache entries")
            else:
                # پاک کردن همه cache
                self.memory_cache.clear()
                logger.info("All cache entries invalidated")
        
        # به‌روزرسانی database cache timestamp to force refresh
        try:
            if hasattr(self.db, 'transaction'):
                with self.db.transaction() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        UPDATE ua_stats_cache 
                        SET updated_at = (CURRENT_TIMESTAMP - INTERVAL '1 hour')
                        WHERE id = 1
                        """
                    )
        except Exception as e:
            logger.error(f"Error invalidating database cache: {e}")
    
    def batch_get_users(self, user_ids: List[int]) -> Dict[int, Dict]:
        """دریافت batch اطلاعات کاربران برای جلوگیری از N+1 queries"""
        if not user_ids:
            return {}
        
        cache_key = f'users_{hash(tuple(sorted(user_ids)))}'
        
        # بررسی memory cache
        if cache_key in self.memory_cache:
            cached = self.memory_cache[cache_key]
            if self._is_cache_valid(cached.get('timestamp')):
                logger.debug(f"Batch users retrieved from cache")
                return cached['data']
        
        try:
            if not hasattr(self.db, 'get_connection'):
                return {}
            
            placeholders = ','.join(['%s'] * len(user_ids))
            query = f"""
                SELECT user_id, username, first_name
                FROM users
                WHERE user_id IN ({placeholders})
            """
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, tuple(user_ids))
                rows = cursor.fetchall()
            
            users = {row['user_id']: dict(row) for row in rows}
            
            # ذخیره در memory cache
            with self.lock:
                self.memory_cache[cache_key] = {
                    'data': users,
                    'timestamp': datetime.now().isoformat()
                }
            
            return users
            
        except Exception as e:
            logger.error(f"Error batch getting users: {e}")
            return {}


# Decorator برای cache کردن نتایج توابع
def cache_result(ttl_seconds: int = 300):
    """Decorator برای cache کردن نتایج توابع"""
    
    def decorator(func):
        cache = {}
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # ساخت cache key
            cache_key = f"{func.__name__}_{str(args)}_{str(kwargs)}"
            
            # بررسی cache
            if cache_key in cache:
                cached_data, cached_time = cache[cache_key]
                if time.time() - cached_time < ttl_seconds:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return cached_data
            
            # اجرای تابع
            result = func(*args, **kwargs)
            
            # ذخیره در cache
            cache[cache_key] = (result, time.time())
            logger.debug(f"Cache miss for {func.__name__}, result cached")
            
            return result
        
        # اضافه کردن متد برای clear کردن cache
        def clear_cache():
            cache.clear()
            logger.debug(f"Cache cleared for {func.__name__}")
        
        wrapper.clear_cache = clear_cache
        return wrapper
    
    return decorator


# Singleton instance
_cache_instance = None

def get_ua_cache(db_adapter, ttl_seconds: int = 300) -> UACache:
    """دریافت singleton instance از cache manager"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = UACache(db_adapter, ttl_seconds)
    return _cache_instance
