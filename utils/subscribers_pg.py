"""
مدیریت لیست مشترکین (کاربران برای ارسال نوتیفیکیشن) - PostgreSQL Backend
این ماژول جایگزین subscribers.py می‌شود و از PostgreSQL استفاده می‌کند
"""
from __future__ import annotations
import os
from typing import List
import logging

logger = logging.getLogger(__name__)


class SubscribersPostgres:
    """مدیریت مشترکین با PostgreSQL Backend"""
    
    def __init__(self, database_url: str = None, db_adapter=None):
        """
        Args:
            database_url: PostgreSQL connection string (اختیاری - از env می‌خواند)
        """
        # Use central DatabaseAdapter (singleton) unless an adapter is provided
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

        # Ensure schema exists (self-healing) via pooled connection
        try:
            self._ensure_schema()
        except Exception as e:
            logger.warning(f"Could not ensure subscribers schema: {e}")
        logger.info("SubscribersPostgres initialized")
    
    def _get_connection(self):
        """دریافت connection به PostgreSQL"""
        # Delegate to adapter's pooled connection
        # DatabaseAdapter forwards get_connection() to underlying PostgreSQL pool
        return self.db.get_connection()
    
    def _ensure_schema(self) -> None:
        """Ensure required table for subscribers exists"""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS subscribers (
                  user_id BIGINT PRIMARY KEY,
                  is_active BOOLEAN NOT NULL DEFAULT TRUE,
                  subscribed_at TIMESTAMP NOT NULL DEFAULT NOW()
                );
                """
            )
            conn.commit()
    def add(self, user_id: int) -> bool:
        """
        افزودن کاربر به لیست مشترکین
        
        Args:
            user_id: شناسه کاربر
            
        Returns:
            True اگر کاربر جدید اضافه شد، False اگر قبلاً وجود داشت
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # چک کردن وجود کاربر
                cursor.execute("""
                    SELECT is_active FROM subscribers WHERE user_id = %s
                """, (user_id,))
                
                existing = cursor.fetchone()
                
                if existing:
                    # اگر قبلاً unsubscribe کرده بود، دوباره فعال کن
                    # Handle both dict-row and tuple-row
                    is_active = existing.get('is_active') if hasattr(existing, 'get') else existing[0]
                    if not bool(is_active):
                        cursor.execute("""
                            UPDATE subscribers 
                            SET is_active = TRUE 
                            WHERE user_id = %s
                        """, (user_id,))
                        conn.commit()
                        cursor.close()
                        logger.info(f"Subscriber reactivated: {user_id}")
                        return True
                    else:
                        cursor.close()
                        return False  # قبلاً فعال بوده
                else:
                    # کاربر جدید
                    cursor.execute("""
                        INSERT INTO subscribers (user_id, is_active)
                        VALUES (%s, TRUE)
                    """, (user_id,))
                    conn.commit()
                    cursor.close()
                    logger.info(f"New subscriber added: {user_id}")
                    return True
                    
        except Exception as e:
            logger.error(f"Error adding subscriber {user_id}: {e}")
            return False
    
    def remove(self, user_id: int) -> bool:
        """
        حذف کاربر از لیست مشترکین (soft delete با is_active=False)
        
        Args:
            user_id: شناسه کاربر
            
        Returns:
            True اگر کاربر حذف شد، False اگر وجود نداشت
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Soft delete - set is_active = FALSE
                cursor.execute("""
                    UPDATE subscribers 
                    SET is_active = FALSE 
                    WHERE user_id = %s AND is_active = TRUE
                    RETURNING user_id
                """, (user_id,))
                
                removed = cursor.fetchone() is not None
                conn.commit()
                cursor.close()
                
                if removed:
                    logger.info(f"Subscriber removed: {user_id}")
                
                return removed
                
        except Exception as e:
            logger.error(f"Error removing subscriber {user_id}: {e}")
            return False
    
    def all(self) -> List[int]:
        """
        دریافت لیست تمام مشترکین فعال
        
        Returns:
            لیست user_id های مشترکین فعال
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT user_id 
                    FROM subscribers 
                    WHERE is_active = TRUE
                    ORDER BY subscribed_at
                """)
                
                subscribers = [row['user_id'] for row in cursor.fetchall()]
                cursor.close()
                
                return subscribers
                
        except Exception as e:
            logger.error(f"Error getting all subscribers: {e}")
            return []
    
    def count(self) -> int:
        """
        دریافت تعداد مشترکین فعال
        
        Returns:
            تعداد مشترکین
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT COUNT(*) AS count 
                    FROM subscribers 
                    WHERE is_active = TRUE
                """)
                
                row = cursor.fetchone()
                count = int(row.get('count') or 0) if row else 0
                cursor.close()
                
                return count
                
        except Exception as e:
            logger.error(f"Error counting subscribers: {e}")
            return 0
    
    def is_subscribed(self, user_id: int) -> bool:
        """
        چک کردن عضویت کاربر در لیست مشترکین
        
        Args:
            user_id: شناسه کاربر
            
        Returns:
            True اگر مشترک فعال باشد
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT is_active 
                    FROM subscribers 
                    WHERE user_id = %s
                """, (user_id,))
                
                result = cursor.fetchone()
                cursor.close()
                
                return bool(result['is_active']) if result else False
                
        except Exception as e:
            logger.error(f"Error checking subscription for {user_id}: {e}")
            return False
    
    def get_inactive_count(self) -> int:
        """
        دریافت تعداد مشترکین غیرفعال (unsubscribed)
        
        Returns:
            تعداد مشترکین غیرفعال
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    SELECT COUNT(*) AS count 
                    FROM subscribers 
                    WHERE is_active = FALSE
                """)
                
                row = cursor.fetchone()
                count = int(row.get('count') or 0) if row else 0
                cursor.close()
                
                return count
                
        except Exception as e:
            logger.error(f"Error counting inactive subscribers: {e}")
            return 0
