"""
PostgreSQL Proxy Implementation
این proxy تمام متدهای database را با PostgreSQL پیاده‌سازی می‌کند
"""

from .database_pg import DatabasePostgres, QueryConverter
from psycopg.errors import UniqueViolation
from typing import List, Dict, Optional, Any, Tuple
from utils.logger import get_logger, log_exception
from config.config import WEAPON_CATEGORIES
from core.cache.cache_manager import cached

logger = get_logger('database.pg_proxy', 'database.log')


class DatabasePostgresProxy(DatabasePostgres):
    """
    PostgreSQL Database Proxy
    این کلاس تمام متدهای database را با PostgreSQL پیاده‌سازی می‌کند
    
    Strategy:
    - برای read operations: از execute_query استفاده می‌کند
    - برای write operations: از transaction استفاده می‌کند
    - تمام queries به PostgreSQL format تبدیل می‌شوند
    """
    
    def __init__(self, database_url: str = None):
        """Initialize PostgreSQL proxy"""
        super().__init__(database_url)
    
    # ==========================================================================
    # Weapon Category Methods
    # ==========================================================================
    
    def get_weapons_in_category(self, category: str, include_inactive: bool = False) -> List[str]:
        """دریافت لیست سلاح‌های یک دسته"""
        try:
            if include_inactive:
                query = """
                    SELECT w.name 
                    FROM weapons w
                    JOIN weapon_categories c ON w.category_id = c.id
                    WHERE c.name = %s
                    ORDER BY w.name
                """
            else:
                query = """
                    SELECT w.name 
                    FROM weapons w
                    JOIN weapon_categories c ON w.category_id = c.id
                    WHERE c.name = %s AND COALESCE(w.is_active, TRUE) = TRUE
                    ORDER BY w.name
                """
            
            results = self.execute_query(query, (category,), fetch_all=True)
            return [row['name'] for row in results]
            
        except Exception as e:
            log_exception(logger, e, f"get_weapons_in_category({category})")
            return []

    def get_weapon_attachments(self, category: str, weapon_name: str, mode: str) -> Dict[str, List[Dict]]:
        """دریافت اتچمنت‌های یک سلاح برای یک mode خاص"""
        try:
            query = """
                SELECT a.id, a.code, a.name, a.image_file_id, a.is_top, a.is_season_top, 
                       a.views_count, a.shares_count
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE c.name = %s AND w.name = %s AND a.mode = %s
                ORDER BY a.is_top DESC, a.order_index ASC, a.name ASC
            """
            
            results = self.execute_query(query, (category, weapon_name, mode), fetch_all=True)
            
            all_attachments = []
            top_attachments = []
            
            for row in results:
                att = dict(row)
                all_attachments.append(att)
                if att.get('is_top'):
                    top_attachments.append(att)
            
            return {
                'top_attachments': top_attachments,
                'all_attachments': all_attachments
            }
            
        except Exception as e:
            log_exception(logger, e, f"get_weapon_attachments({category}, {weapon_name}, {mode})")
            return {'top_attachments': [], 'all_attachments': []}

    def search(self, query_text: str) -> List[Dict]:
        """جستجوی اتچمنت‌ها بر اساس نام، کد یا نام سلاح"""
        try:
            # جستجو در نام اتچمنت، کد اتچمنت، یا نام سلاح
            # از ILIKE برای case-insensitive matching استفاده می‌کنیم
            sql = """
                SELECT a.id, a.code, a.name, a.image_file_id as image, a.mode,
                       w.name as weapon, c.name as category
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE a.name ILIKE %s 
                   OR a.code ILIKE %s 
                   OR w.name ILIKE %s
                ORDER BY w.name, a.mode, a.name
                LIMIT 50
            """
            
            search_term = f"%{query_text}%"
            params = (search_term, search_term, search_term)
            
            results = self.execute_query(sql, params, fetch_all=True)
            
            # تبدیل به فرمت مورد انتظار Handler
            # Handler انتظار لیستی از دیکشنری‌ها را دارد که کلیدهای
            # category, weapon, mode, attachment (dict) را داشته باشند
            # اما طبق خط 209-210 handelr، اگر لیست باشد آیتم‌ها را append می‌کند
            # و در خط 213: item['attachment'] دسترسی پیدا می‌کند.
            # پس ساختار هر آیتم باید این باشد:
            # {
            #    'category': ..., 'weapon': ..., 'mode': ...,
            #    'attachment': {'name': ..., 'code': ..., 'image': ...}
            # }
            
            formatted_results = []
            for row in results:
                formatted_results.append({
                    'category': row['category'],
                    'weapon': row['weapon'],
                    'mode': row['mode'],
                    'attachment': {
                        'id': row['id'],
                        'name': row['name'],
                        'code': row['code'],
                        'image': row['image']
                    }
                })
            
            return formatted_results
            
        except Exception as e:
            log_exception(logger, e, f"search({query_text})")
            return []

    def set_top_attachments(self, category: str, weapon_name: str,
                            attachment_codes: List[str], mode: str = "br") -> bool:
        """
        تنظیم اتچمنت‌های برتر برای یک سلاح/مود (PostgreSQL)
        - تمام اتچمنت‌های سلاح در مود مشخص ابتدا از حالت برتر خارج می‌شوند
        - سپس کدهای ورودی به ترتیب داده‌شده به عنوان برتر علامت می‌خورند و order_index تنظیم می‌شود
        """
        try:
            # محدود به حداکثر 5 مورد مطابق UI
            codes = list(dict.fromkeys(attachment_codes))[:5]
            if not codes:
                logger.warning("set_top_attachments called with empty codes list")
                return True

            with self.transaction() as conn:
                cursor = conn.cursor()

                # دریافت weapon_id
                cursor.execute(
                    """
                    SELECT w.id FROM weapons w
                    JOIN weapon_categories c ON w.category_id = c.id
                    WHERE c.name = %s AND w.name = %s
                    """,
                    (category, weapon_name),
                )
                res = cursor.fetchone()
                if not res:
                    cursor.close()
                    logger.error(f"Weapon not found for set_top_attachments: {category}/{weapon_name}")
                    return False
                weapon_id = res["id"]

                # 1) همه را از Top خارج کن
                cursor.execute(
                    """
                    UPDATE attachments
                    SET is_top = FALSE, updated_at = NOW()
                    WHERE weapon_id = %s AND mode = %s
                    """,
                    (weapon_id, mode),
                )

                # 2) فقط انتخابی‌ها را Top و order_index بده
                # ساخت CASE برای order_index
                case_parts = []
                params = []
                for idx, code in enumerate(codes, start=1):
                    case_parts.append("WHEN code = %s THEN %s")
                    params.extend([code, idx])

                case_sql = " ".join(case_parts)

                # UPDATE فقط برای کدهای انتخاب‌شده
                in_placeholders = ", ".join(["%s"] * len(codes))
                params.extend([weapon_id, mode, *codes])

                update_sql = f"""
                    UPDATE attachments
                    SET is_top = TRUE,
                        order_index = CASE {case_sql} ELSE order_index END,
                        updated_at = NOW()
                    WHERE weapon_id = %s AND mode = %s AND code IN ({in_placeholders})
                """

                cursor.execute(update_sql, tuple(params))
                cursor.close()

                logger.info(
                    f"✅ Top attachments set: {category}/{weapon_name} ({mode}) -> {codes}"
                )
                return True
        except Exception as e:
            log_exception(logger, e, f"set_top_attachments({category}, {weapon_name})")
            return False

    def edit_attachment(
        self,
        category: str,
        weapon_name: str,
        code: str,
        new_name: str = None,
        new_image: str = None,
        new_code: str = None,
        mode: str = "br",
    ) -> bool:
        """
        ویرایش اتچمنت (wrapper سازگار با نسخه‌های قدیمی)
        - اگر new_name/new_image داده شود، فیلدهای مربوطه آپدیت می‌شوند
        - اگر new_code داده شود، کد تغییر می‌کند
        """
        try:
            success = True

            if new_name is not None or new_image is not None:
                # استفاده از متد عمومی update_attachment
                ok = self.update_attachment(
                    attachment_id=None,
                    category=category,
                    weapon_name=weapon_name,
                    mode=mode,
                    code=code,
                    name=new_name,
                    image=new_image,
                )
                success = success and ok

            if new_code:
                ok = self.update_attachment_code(
                    category=category,
                    weapon_name=weapon_name,
                    old_code=code,
                    new_code=new_code,
                    mode=mode,
                )
                success = success and ok

            return success
        except Exception as e:
            log_exception(logger, e, f"edit_attachment({category}, {weapon_name}, {code})")
            return False
    
    def add_weapon(self, category: str, weapon_name: str) -> bool:
        """افزودن سلاح جدید"""
        try:
            # پیدا کردن category_id
            query1 = "SELECT id FROM weapon_categories WHERE name = %s"
            result = self.execute_query(query1, (category,), fetch_one=True)
            
            if not result:
                logger.error(f"Category '{category}' not found")
                return False
            
            category_id = result['id']
            
            # افزودن سلاح
            query2 = """
                INSERT INTO weapons (category_id, name, created_at)
                VALUES (%s, %s, NOW())
            """
            
            self.execute_query(query2, (category_id, weapon_name))
            logger.info(f"✅ Weapon added: {weapon_name} in {category}")
            return True
        except UniqueViolation:
            # سلاح از قبل در این دسته وجود دارد - برای seeding دوباره، این وضعیت موفقیت محسوب می‌شود
            logger.info(f"Weapon already exists, skipping: {weapon_name} in {category}")
            return True
        except Exception as e:
            log_exception(logger, e, f"add_weapon({category}, {weapon_name})")
            return False
    
    def get_all_category_counts(self) -> Dict[str, int]:
        """دریافت تعداد سلاح‌های همه دسته‌ها"""
        try:
            query = """
                SELECT c.name, COUNT(w.id) as count
                FROM weapon_categories c
                LEFT JOIN weapons w ON c.id = w.category_id
                GROUP BY c.name
            """
            
            results = self.execute_query(query, fetch_all=True)
            return {row['name']: row['count'] for row in results}
            
        except Exception as e:
            log_exception(logger, e, "get_all_category_counts")
            return {}
    
    # ==========================================================================
    # Blacklist Methods
    # ==========================================================================
    
    def get_all_blacklisted_words(self) -> List[Dict]:
        """دریافت لیست کلمات ممنوع"""
        try:
            query = """
                SELECT * FROM blacklisted_words
                ORDER BY word ASC
            """
            return self.execute_query(query, fetch_all=True)
        except Exception as e:
            log_exception(logger, e, "get_all_blacklisted_words")
            return []

    # ==========================================================================
    # User Helper Methods (for UA ban/unban flows)
    # ==========================================================================
    def get_user(self, user_id: int) -> Optional[Dict]:
        """
        دریافت اطلاعات کاربر از جدول users
        Returns: dict یا None
        """
        try:
            query = """
                SELECT user_id, username, first_name
                FROM users
                WHERE user_id = %s
            """
            return self.execute_query(query, (user_id,), fetch_one=True)
        except Exception as e:
            log_exception(logger, e, f"get_user({user_id})")
            return None

    def get_user_language(self, user_id: int) -> Optional[str]:
        """
        دریافت زبان کاربر از جدول users
        Returns: 'fa' | 'en' | None
        """
        try:
            query = "SELECT language FROM users WHERE user_id = %s"
            result = self.execute_query(query, (user_id,), fetch_one=True)
            if result:
                return result.get('language')
            return None
        except Exception as e:
            log_exception(logger, e, f"get_user_language({user_id})")
            return None

    def set_user_language(self, user_id: int, lang: str) -> bool:
        """
        تنظیم زبان کاربر در جدول users (fa/en)
        اگر کاربر وجود نداشت، ساخته می‌شود.
        """
        if lang not in ('fa', 'en'):
            logger.error(f"Invalid language: {lang}")
            return False
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (user_id, language)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id)
                    DO UPDATE SET language = EXCLUDED.language
                    """,
                    (user_id, lang)
                )
                cursor.close()
                logger.info(f"✅ Language set: user={user_id}, lang={lang}")
                return True
        except Exception as e:
            log_exception(logger, e, f"set_user_language({user_id}, {lang})")
            return False

    def unban_user_from_attachments(self, user_id: int) -> bool:
        """
        رفع محرومیت کاربر از ارسال اتچمنت‌ها
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE user_submission_stats
                    SET is_banned = FALSE, updated_at = NOW()
                    WHERE user_id = %s AND is_banned = TRUE
                    """,
                    (user_id,),
                )
                affected = getattr(cursor, 'rowcount', None)
                cursor.close()
                if affected is not None and affected == 0:
                    logger.warning(f"No banned record found to unban for user_id={user_id}")
                    return False
            logger.info(f"✅ User unbanned from attachments: {user_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"unban_user_from_attachments({user_id})")
            return False

    # Role Management Methods
    # ==========================================================================    
    def create_role_if_not_exists(self, role_name: str, display_name: str, 
                                   description: str = '', icon: str = '', 
                                   permissions: List[str] = None) -> bool:
        """ایجاد role اگر وجود نداشته باشد"""
        permissions = permissions or []
        
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # بررسی وجود role
                query_check = "SELECT id FROM roles WHERE name = %s"
                cursor.execute(query_check, (role_name,))
                result = cursor.fetchone()
                
                if result:
                    role_id = result['id']
                    # Update existing role
                    query_update = """
                        UPDATE roles 
                        SET display_name = %s, description = %s, icon = %s
                        WHERE id = %s
                    """
                    cursor.execute(query_update, (display_name, description, icon, role_id))
                else:
                    # Insert new role
                    query_insert = """
                        INSERT INTO roles (name, display_name, description, icon, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        RETURNING id
                    """
                    cursor.execute(query_insert, (role_name, display_name, description, icon))
                    result = cursor.fetchone()
                    role_id = result['id']
                
                # حذف permissions قدیمی
                query_delete = "DELETE FROM role_permissions WHERE role_id = %s"
                cursor.execute(query_delete, (role_id,))
                # اضافه کردن permissions جدید
                for perm in permissions:
                    query_perm = """
                        INSERT INTO role_permissions (role_id, permission)
                        VALUES (%s, %s)
                    """
                    cursor.execute(query_perm, (role_id, perm))
                
                cursor.close()
                logger.info(f"✅ Role created/updated: {role_name}")
                return True
                
        except Exception as e:
            log_exception(logger, e, f"create_role_if_not_exists({role_name})")
            return False
    
    # ==========================================================================
    # Phase 1: Attachment Operations - Day 1
    # ==========================================================================
    
    def add_attachment(self, category: str, weapon_name: str, code: str,
                      name: str, image: str = None, is_top: bool = False,
                      is_season_top: bool = False, mode: str = "br") -> bool:
        """
        افزودن اتچمنت جدید - PostgreSQL Implementation
        
        Args:
            category: دسته سلاح (assault_rifle, smg, ...)
            weapon_name: نام سلاح
            code: کد اتچمنت
            name: نام اتچمنت
            image: file_id تصویر
            is_top: آیا جزو top 5 است؟
            is_season_top: آیا جزو season top است؟
            mode: mp یا br
        
        Returns:
            bool: True در صورت موفقیت
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # 1. پیدا کردن weapon_id
                query_weapon = """
                    SELECT w.id FROM weapons w
                    JOIN weapon_categories c ON w.category_id = c.id
                    WHERE c.name = %s AND w.name = %s
                """
                cursor.execute(query_weapon, (category, weapon_name))
                result = cursor.fetchone()
                
                if not result:
                    # اگر سلاح وجود ندارد، ابتدا آن را بساز
                    cursor.close()
                    if not self.add_weapon(category, weapon_name):
                        return False
                    
                    # دوباره weapon_id را بگیر
                    cursor = conn.cursor()
                    cursor.execute(query_weapon, (category, weapon_name))
                    result = cursor.fetchone()
                    
                    if not result:
                        cursor.close()
                        logger.error(f"Failed to create weapon: {weapon_name} in {category}")
                        return False
                
                weapon_id = result['id']
                
                # 2. افزودن/بروزرسانی attachment
                query_insert = """
                    INSERT INTO attachments (
                        weapon_id, mode, code, name, image_file_id,
                        is_top, is_season_top, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (weapon_id, mode, code)
                    DO UPDATE SET
                        name = EXCLUDED.name,
                        image_file_id = EXCLUDED.image_file_id,
                        is_top = EXCLUDED.is_top,
                        is_season_top = EXCLUDED.is_season_top,
                        updated_at = NOW()
                """
                
                cursor.execute(
                    query_insert,
                    (weapon_id, mode, code, name, image, is_top, is_season_top)
                )
                
                cursor.close()
                logger.info(f"✅ Attachment added/updated (PostgreSQL): {code} for {weapon_name}")
                return True
                
        except Exception as e:
            log_exception(logger, e, f"add_attachment({category}, {weapon_name}, {code})")
            return False
    
    def get_top_attachments(self, category: str, weapon_name: str, mode: str = "br") -> List[Dict]:
        """
        دریافت 5 اتچمنت برتر
        
        Args:
            category: دسته سلاح
            weapon_name: نام سلاح
            mode: mp یا br
        
        Returns:
            List[Dict]: لیست اتچمنت‌های برتر
        """
        try:
            query = """
                SELECT 
                    a.id, a.code, a.name, 
                    a.image_file_id as image,
                    a.is_top, a.is_season_top as season_top
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE c.name = %s 
                  AND w.name = %s 
                  AND a.mode = %s 
                  AND a.is_top = TRUE
                ORDER BY a.order_index NULLS LAST, a.id
                LIMIT 5
            """
            
            results = self.execute_query(
                query,
                (category, weapon_name, mode),
                fetch_all=True
            )
            
            logger.debug(f"✅ Found {len(results)} top attachments for {weapon_name}")
            return results
            
        except Exception as e:
            log_exception(logger, e, f"get_top_attachments({category}, {weapon_name})")
            return []
    
    def get_all_attachments(self, category: str, weapon_name: str, mode: str = "br") -> List[Dict]:
        """
        دریافت تمام اتچمنت‌های یک سلاح
        
        Args:
            category: دسته سلاح
            weapon_name: نام سلاح
            mode: mp یا br
        
        Returns:
            List[Dict]: لیست تمام اتچمنت‌ها
        """
        try:
            query = """
                SELECT 
                    a.id, a.code, a.name,
                    a.image_file_id as image,
                    a.is_top as top, 
                    a.is_season_top as season_top
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE c.name = %s 
                  AND w.name = %s 
                  AND a.mode = %s
                ORDER BY a.is_top DESC, a.is_season_top DESC, a.id
            """
            
            results = self.execute_query(
                query,
                (category, weapon_name, mode),
                fetch_all=True
            )
            
            logger.debug(f"✅ Found {len(results)} attachments for {weapon_name}")
            return results
            
        except Exception as e:
            log_exception(logger, e, f"get_all_attachments({category}, {weapon_name})")
            return []
    
    def update_attachment(self, attachment_id: int = None, category: str = None,
                         weapon_name: str = None, mode: str = None, code: str = None,
                         name: str = None, image: str = None, 
                         is_top: bool = None, is_season_top: bool = None) -> bool:
        """
        ویرایش اتچمنت
        
        Args:
            attachment_id: ID اتچمنت (اگر مشخص باشد)
            یا ترکیب category, weapon_name, mode, code
            
        Returns:
            bool: True در صورت موفقیت
        """
        try:
            updates = []
            params = []
            
            if name is not None:
                updates.append("name = %s")
                params.append(name)
            
            if image is not None:
                updates.append("image_file_id = %s")
                params.append(image)
            
            if is_top is not None:
                updates.append("is_top = %s")
                params.append(is_top)
            
            if is_season_top is not None:
                updates.append("is_season_top = %s")
                params.append(is_season_top)
            
            if not updates:
                logger.warning("No updates provided for attachment")
                return False
            
            # اضافه کردن updated_at
            updates.append("updated_at = NOW()")
            
            # ساخت WHERE clause
            if attachment_id is not None:
                where_clause = "id = %s"
                params.append(attachment_id)
            elif all([category, weapon_name, mode, code]):
                where_clause = """
                    weapon_id = (
                        SELECT w.id FROM weapons w
                        JOIN weapon_categories c ON w.category_id = c.id
                        WHERE c.name = %s AND w.name = %s
                    ) AND mode = %s AND code = %s
                """
                params.extend([category, weapon_name, mode, code])
            else:
                logger.error("Either attachment_id or (category, weapon, mode, code) required")
                return False
            
            query = f"""
                UPDATE attachments
                SET {', '.join(updates)}
                WHERE {where_clause}
            """
            
            self.execute_query(query, tuple(params))
            logger.info(f"✅ Attachment updated (PostgreSQL)")
            return True
            
        except Exception as e:
            log_exception(logger, e, f"update_attachment")
            return False
    
    def delete_attachment(self, attachment_id: int = None, category: str = None,
                         weapon_name: str = None, mode: str = None, code: str = None) -> bool:
        """
        حذف اتچمنت
        
        Args:
            attachment_id: ID اتچمنت
            یا ترکیب category, weapon_name, mode, code
        
        Returns:
            bool: True در صورت موفقیت
        """
        try:
            if attachment_id is not None:
                query = "DELETE FROM attachments WHERE id = %s"
                params = (attachment_id,)
            elif all([category, weapon_name, mode, code]):
                query = """
                    DELETE FROM attachments
                    WHERE weapon_id = (
                        SELECT w.id FROM weapons w
                        JOIN weapon_categories c ON w.category_id = c.id
                        WHERE c.name = %s AND w.name = %s
                    ) AND mode = %s AND code = %s
                """
                params = (category, weapon_name, mode, code)
            else:
                logger.error("Either attachment_id or (category, weapon, mode, code) required")
                return False
            
            self.execute_query(query, params)
            logger.info(f"✅ Attachment deleted (PostgreSQL)")
            return True
            
        except Exception as e:
            log_exception(logger, e, f"delete_attachment")
            return False
    
    def update_attachment_code(self, category: str, weapon_name: str, old_code: str, 
                               new_code: str, mode: str = "br") -> bool:
        """
        به‌روزرسانی کد اتچمنت
        
        Args:
            category: دسته‌بندی سلاح
            weapon_name: نام سلاح
            old_code: کد قدیمی اتچمنت
            new_code: کد جدید اتچمنت
            mode: مود بازی ('br' یا 'mp')
        
        Returns:
            bool: True در صورت موفقیت
        """
        try:
            query = """
                UPDATE attachments 
                SET code = %s
                WHERE weapon_id = (
                    SELECT w.id FROM weapons w
                    JOIN weapon_categories c ON w.category_id = c.id
                    WHERE c.name = %s AND w.name = %s
                )
                AND code = %s AND mode = %s
            """
            
            result = self.execute_query(query, (new_code, category, weapon_name, old_code, mode))
            
            # بررسی تعداد ردیف‌های تغییریافته
            if result and hasattr(result, 'rowcount'):
                success = result.rowcount > 0
            else:
                # اگر execute_query مستقیماً None برگرداند، موفقیت‌آمیز بوده
                success = True
            
            if success:
                logger.info(f"✅ Attachment code updated: {old_code} → {new_code} (PostgreSQL)")
            else:
                logger.warning(f"⚠️ No attachment found to update: {category}/{weapon_name}/{old_code}")
            
            return success
            
        except Exception as e:
            log_exception(logger, e, f"update_attachment_code({category}, {weapon_name}, {old_code}, {new_code})")
            return False
    
    def get_attachment_by_id(self, attachment_id: int) -> Optional[Dict]:
        """
        دریافت اطلاعات کامل یک اتچمنت با ID
        
        Args:
            attachment_id: ID اتچمنت
        
        Returns:
            Dict: اطلاعات اتچمنت یا None
        """
        try:
            query = """
                SELECT 
                    a.id, a.code, a.name, a.mode,
                    a.image_file_id as image,
                    w.name AS weapon,
                    c.name AS category
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE a.id = %s
            """
            
            result = self.execute_query(query, (attachment_id,), fetch_one=True)
            
            if result:
                logger.debug(f"✅ Attachment found: ID={attachment_id}")
            else:
                logger.debug(f"Attachment not found: ID={attachment_id}")
            
            return result
            
        except Exception as e:
            log_exception(logger, e, f"get_attachment_by_id({attachment_id})")
            return None
    
    def get_attachment_code_by_id(self, attachment_id: int) -> Optional[str]:
        """
        دریافت فقط کد اتچمنت با ID
        
        Args:
            attachment_id: ID اتچمنت
        
        Returns:
            str: کد اتچمنت یا None
        """
        try:
            query = "SELECT code FROM attachments WHERE id = %s"
            result = self.execute_query(query, (attachment_id,), fetch_one=True)
            
            return result['code'] if result else None
            
        except Exception as e:
            log_exception(logger, e, f"get_attachment_code_by_id({attachment_id})")
            return None
    
    def get_season_top_attachments_for_weapon(self, category: str, weapon_name: str, 
                                             mode: str = "br") -> List[Dict]:
        """
        دریافت برترین‌های فصل برای یک سلاح خاص
        
        Args:
            category: دسته سلاح
            weapon_name: نام سلاح
            mode: mp یا br
        
        Returns:
            List[Dict]: لیست اتچمنت‌های season_top
        """
        try:
            query = """
                SELECT 
                    a.code, a.name, 
                    a.image_file_id as image
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE c.name = %s 
                  AND w.name = %s 
                  AND a.mode = %s 
                  AND a.is_season_top = TRUE
                ORDER BY a.id
            """
            
            results = self.execute_query(
                query,
                (category, weapon_name, mode),
                fetch_all=True
            )
            
            # اضافه کردن season_top flag
            attachments = []
            for row in results:
                att = row
                att['season_top'] = True
                attachments.append(att)
            
            logger.debug(f"✅ Found {len(attachments)} season top attachments")
            return attachments
            
        except Exception as e:
            log_exception(logger, e, f"get_season_top_attachments_for_weapon")
            return []
    
    def get_season_top_attachments(self, mode: str = None) -> List[Dict]:
        """
        دریافت همه برترین‌های فصل
        
        Args:
            mode: mp, br یا None برای همه
        
        Returns:
            List[Dict]: لیست (category, weapon, mode, attachment_dict)
        """
        try:
            if mode:
                query = """
                    SELECT 
                        c.name as category, 
                        w.name as weapon, 
                        a.mode,
                        a.id, a.code, 
                        a.name as att_name, 
                        a.image_file_id as image
                    FROM attachments a
                    JOIN weapons w ON a.weapon_id = w.id
                    JOIN weapon_categories c ON w.category_id = c.id
                    WHERE a.is_season_top = TRUE AND a.mode = %s
                    ORDER BY c.id, w.name
                """
                results = self.execute_query(query, (mode,), fetch_all=True)
            else:
                query = """
                    SELECT 
                        c.name as category, 
                        w.name as weapon, 
                        a.mode,
                        a.id, a.code, 
                        a.name as att_name, 
                        a.image_file_id as image
                    FROM attachments a
                    JOIN weapons w ON a.weapon_id = w.id
                    JOIN weapon_categories c ON w.category_id = c.id
                    WHERE a.is_season_top = TRUE
                    ORDER BY c.id, w.name, a.mode
                """
                results = self.execute_query(query, fetch_all=True)
            
            # تبدیل به format مورد نظر
            items = []
            for row in results:
                items.append({
                    'category': row['category'],
                    'weapon': row['weapon'],
                    'mode': row['mode'],
                    'attachment': {
                        'id': row['id'],
                        'code': row['code'],
                        'name': row['att_name'],
                        'image': row['image']
                    }
                })
            
            logger.debug(f"✅ Found {len(items)} season top attachments")
            return items
            
        except Exception as e:
            log_exception(logger, e, "get_season_top_attachments")
            return []

    # ==========================================================================
    # Scheduled Notifications Methods
    # ==========================================================================
    def create_scheduled_notification(
        self,
        message_type: str,
        message_text: str = None,
        photo_file_id: str = None,
        parse_mode: str = 'Markdown',
        interval_hours: int = 24,
        next_run_at = None,
        enabled: bool = True,
        created_by: int = None,
    ) -> Optional[int]:
        """ایجاد یک اعلان زمان‌بندی شده جدید و برگرداندن id"""
        try:
            query = (
                """
                INSERT INTO scheduled_notifications (
                  message_type, message_text, photo_file_id, parse_mode,
                  interval_hours, enabled, last_sent_at, next_run_at,
                  created_by, created_at, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW(), NOW())
                RETURNING id
                """
            )
            row = self.execute_query(
                query,
                (
                    message_type, message_text, photo_file_id, parse_mode,
                    interval_hours, enabled, None, next_run_at,
                    created_by,
                ),
                fetch_one=True,
            )
            return row['id'] if row else None
        except Exception as e:
            log_exception(logger, e, "create_scheduled_notification")
            return None

    def update_scheduled_notification(
        self,
        schedule_id: int,
        message_type: Optional[str] = None,
        message_text: Optional[str] = None,
        photo_file_id: Optional[str] = None,
        parse_mode: Optional[str] = None,
        interval_hours: Optional[int] = None,
        next_run_at: Optional[Any] = None,
        enabled: Optional[bool] = None,
    ) -> bool:
        """به‌روزرسانی فیلدهای زمان‌بندی اعلان."""
        try:
            sets = []
            params: list[Any] = []

            if message_type is not None:
                sets.append("message_type = %s")
                params.append(message_type)
            if message_text is not None:
                sets.append("message_text = %s")
                params.append(message_text)
            if photo_file_id is not None:
                sets.append("photo_file_id = %s")
                params.append(photo_file_id)
            if parse_mode is not None:
                sets.append("parse_mode = %s")
                params.append(parse_mode)
            if interval_hours is not None:
                sets.append("interval_hours = %s")
                params.append(interval_hours)
            if next_run_at is not None:
                sets.append("next_run_at = %s")
                params.append(next_run_at)
            if enabled is not None:
                sets.append("enabled = %s")
                params.append(enabled)

            if not sets:
                logger.warning("update_scheduled_notification called with no fields to update")
                return False

            sets.append("updated_at = NOW()")
            query = f"""
                UPDATE scheduled_notifications
                SET {', '.join(sets)}
                WHERE id = %s
            """
            params.append(schedule_id)

            self.execute_query(query, tuple(params))
            logger.info(f"✅ Scheduled notification updated: id={schedule_id}")
            return True
        except Exception as e:
            log_exception(logger, e, "update_scheduled_notification")
            return False

    def list_scheduled_notifications(self) -> List[Dict]:
        """دریافت لیست اعلان‌های زمان‌بندی شده"""
        try:
            query = (
                """
                SELECT id, message_type, message_text, photo_file_id, parse_mode,
                       interval_hours, enabled, last_sent_at, next_run_at,
                       created_by, created_at, updated_at
                FROM scheduled_notifications
                ORDER BY enabled DESC, next_run_at NULLS LAST, id DESC
                """
            )
            return self.execute_query(query, fetch_all=True)
        except Exception as e:
            log_exception(logger, e, "list_scheduled_notifications")
            return []

    def delete_scheduled_notification(self, schedule_id: int) -> bool:
        """حذف یک اعلان زمان‌بندی شده"""
        try:
            self.execute_query("DELETE FROM scheduled_notifications WHERE id = %s", (schedule_id,))
            return True
        except Exception as e:
            log_exception(logger, e, "delete_scheduled_notification")
            return False

    def get_due_scheduled_notifications(self, now_ts) -> List[Dict]:
        """
        دریافت اعلان‌های سررسید شده (enabled و next_run_at <= now)
        Args:
            now_ts: datetime with tzinfo (UTC)
        """
        try:
            query = (
                """
                SELECT id, message_type, message_text, photo_file_id, parse_mode,
                       interval_hours, enabled, last_sent_at, next_run_at
                FROM scheduled_notifications
                WHERE enabled = TRUE AND next_run_at IS NOT NULL AND next_run_at <= %s
                ORDER BY next_run_at ASC
                LIMIT 50
                """
            )
            return self.execute_query(query, (now_ts,), fetch_all=True)
        except Exception as e:
            log_exception(logger, e, "get_due_scheduled_notifications")
            return []

    def mark_schedule_sent(self, schedule_id: int, last_sent_at, next_run_at) -> bool:
        """به‌روزرسانی زمان‌های ارسال برای یک اعلان زمان‌بندی شده"""
        try:
            query = (
                """
                UPDATE scheduled_notifications
                SET last_sent_at = %s,
                    next_run_at = %s,
                    updated_at = NOW()
                WHERE id = %s
                """
            )
            self.execute_query(query, (last_sent_at, next_run_at, schedule_id))
            return True
        except Exception as e:
            log_exception(logger, e, "mark_schedule_sent")
            return False

    def set_schedule_enabled(self, schedule_id: int, enabled: bool) -> bool:
        """فعال/غیرفعال کردن یک زمان‌بندی"""
        try:
            query = (
                """
                UPDATE scheduled_notifications
                SET enabled = %s,
                    updated_at = NOW()
                WHERE id = %s
                """
            )
            self.execute_query(query, (enabled, schedule_id))
            return True
        except Exception as e:
            log_exception(logger, e, "set_schedule_enabled")
            return False

    def get_scheduled_notification_by_id(self, schedule_id: int) -> Optional[Dict]:
        """دریافت یک زمان‌بندی بر اساس id"""
        try:
            query = (
                """
                SELECT id, message_type, message_text, photo_file_id, parse_mode,
                       interval_hours, enabled, last_sent_at, next_run_at,
                       created_by, created_at, updated_at
                FROM scheduled_notifications
                WHERE id = %s
                """
            )
            return self.execute_query(query, (schedule_id,), fetch_one=True)
        except Exception as e:
            log_exception(logger, e, "get_scheduled_notification_by_id")
            return None
    def vote_attachment(self, user_id: int, attachment_id: int, vote: int) -> Dict:
        """
        ثبت یا تغییر رأی کاربر برای اتچمنت (Atomic UPSERT - Race-Condition Safe)
        
        Args:
            user_id: شناسه کاربر
            attachment_id: شناسه اتچمنت
            vote: +1 (لایک), -1 (دیس‌لایک), 0 (حذف رأی)
        
        Returns:
            Dict: {success, action, previous_vote, new_vote, like_count, dislike_count}
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # ✅ ATOMIC UPSERT - جلوگیری از race condition
                # ابتدا رأی قبلی را بگیر (با قفل)
                cursor.execute("""
                    SELECT rating FROM user_attachment_engagement
                    WHERE user_id = %s AND attachment_id = %s
                    FOR UPDATE NOWAIT
                """, (user_id, attachment_id))
                
                existing = cursor.fetchone()
                previous_vote = existing['rating'] if existing else None
                
                # تشخیص action و رأی جدید
                if previous_vote is None:
                    # رأی جدید
                    new_rating = vote if vote != 0 else None
                    action = "added" if vote != 0 else "none"
                elif previous_vote == vote:
                    # Toggle: حذف رأی
                    new_rating = None
                    action = "removed"
                elif vote == 0:
                    # حذف صریح
                    new_rating = None
                    action = "removed"
                else:
                    # تغییر رأی
                    new_rating = vote
                    action = "changed"
                
                # UPSERT atomic
                cursor.execute("""
                    INSERT INTO user_attachment_engagement 
                    (user_id, attachment_id, rating, first_view_date, last_view_date)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    ON CONFLICT (user_id, attachment_id) DO UPDATE
                    SET rating = EXCLUDED.rating,
                        last_view_date = NOW()
                """, (user_id, attachment_id, new_rating))
                
                # محاسبه آمار (یک query)
                cursor.execute("""
                    SELECT 
                        COUNT(CASE WHEN rating = 1 THEN 1 END) as likes,
                        COUNT(CASE WHEN rating = -1 THEN 1 END) as dislikes
                    FROM user_attachment_engagement
                    WHERE attachment_id = %s AND rating IS NOT NULL
                """, (attachment_id,))
                
                stats = cursor.fetchone()
                like_count = stats['likes']
                dislike_count = stats['dislikes']
                
                cursor.close()
                
                logger.info(f"✅ Vote (atomic): user={user_id}, att={attachment_id}, "
                           f"{previous_vote}→{new_rating}, action={action}")
                
                return {
                    'success': True,
                    'action': action,
                    'previous_vote': previous_vote,
                    'new_vote': new_rating if new_rating is not None else 0,
                    'like_count': like_count,
                    'dislike_count': dislike_count
                }
                
        except Exception as e:
            log_exception(logger, e, f"vote_attachment({user_id}, {attachment_id})")
            return {
                'success': False,
                'action': 'error',
                'error': str(e)
            }
    
    def get_user_vote(self, attachment_id: int, user_id: int) -> Optional[int]:
        """
        دریافت رأی فعلی کاربر
        
        Returns:
            +1 (لایک), -1 (دیس‌لایک), None (رأی نداده)
        """
        try:
            query = """
                SELECT rating FROM user_attachment_engagement
                WHERE user_id = %s AND attachment_id = %s
            """
            result = self.execute_query(query, (user_id, attachment_id), fetch_one=True)
            
            return result['rating'] if result else None
            
        except Exception as e:
            log_exception(logger, e, f"get_user_vote({attachment_id}, {user_id})")
            return None
    
    def track_attachment_view(self, user_id: int, attachment_id: int) -> bool:
        """
        ثبت بازدید اتچمنت
        
        Returns:
            bool: True در صورت موفقیت
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # بررسی وجود
                cursor.execute("""
                    SELECT total_views FROM user_attachment_engagement
                    WHERE user_id = %s AND attachment_id = %s
                """, (user_id, attachment_id))
                
                existing = cursor.fetchone()
                
                if existing:
                    # به‌روزرسانی
                    cursor.execute("""
                        UPDATE user_attachment_engagement
                        SET total_views = COALESCE(total_views, 0) + 1,
                            last_view_date = NOW()
                        WHERE user_id = %s AND attachment_id = %s
                    """, (user_id, attachment_id))
                else:
                    # ایجاد جدید
                    cursor.execute("""
                        INSERT INTO user_attachment_engagement
                        (user_id, attachment_id, total_views, first_view_date, last_view_date)
                        VALUES (%s, %s, 1, NOW(), NOW())
                    """, (user_id, attachment_id))
                
                cursor.close()
                logger.debug(f"✅ View tracked: user={user_id}, att={attachment_id}")
                return True
                
        except Exception as e:
            log_exception(logger, e, f"track_attachment_view({user_id}, {attachment_id})")
            return False
    
    def track_attachment_copy(self, user_id: int, attachment_id: int) -> bool:
        """
        ثبت کپی کد اتچمنت
        
        Returns:
            bool: True در صورت موفقیت
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # بررسی وجود
                cursor.execute("""
                    SELECT total_clicks FROM user_attachment_engagement
                    WHERE user_id = %s AND attachment_id = %s
                """, (user_id, attachment_id))
                
                existing = cursor.fetchone()
                
                if existing:
                    # به‌روزرسانی
                    cursor.execute("""
                        UPDATE user_attachment_engagement
                        SET total_clicks = COALESCE(total_clicks, 0) + 1,
                            last_view_date = NOW()
                        WHERE user_id = %s AND attachment_id = %s
                    """, (user_id, attachment_id))
                else:
                    # ایجاد جدید
                    cursor.execute("""
                        INSERT INTO user_attachment_engagement
                        (user_id, attachment_id, total_clicks, first_view_date, last_view_date)
                        VALUES (%s, %s, 1, NOW(), NOW())
                    """, (user_id, attachment_id))
                
                cursor.close()
                logger.debug(f"✅ Copy tracked: user={user_id}, att={attachment_id}")
                return True
                
        except Exception as e:
            log_exception(logger, e, f"track_attachment_copy({user_id}, {attachment_id})")
            return False
    
    def get_popular_attachments(self, category: str = None, weapon: str = None,
                               mode: str = None, limit: int = 10, days: int = 14,
                               suggested_only: bool = False) -> List[Dict]:
        """
        دریافت محبوب‌ترین اتچمنت‌ها بر اساس رأی و تعامل
        
        Args:
            category: فیلتر دسته (اختیاری)
            weapon: فیلتر سلاح (اختیاری)
            mode: فیلتر مود (اختیاری)
            limit: تعداد نتایج
            days: محدوده زمانی (روز)
            suggested_only: فقط پیشنهادی‌ها
        
        Returns:
            List[Dict]: لیست اتچمنت‌های محبوب با آمار
        """
        try:
            # ساخت WHERE clauses
            where_clauses = []
            params = []
            
            if category:
                where_clauses.append("wc.name = %s")
                params.append(category)
            
            if weapon:
                where_clauses.append("w.name = %s")
                params.append(weapon)
            
            if mode:
                where_clauses.append("a.mode = %s")
                params.append(mode)
            
            # محدوده زمانی: use parameterized interval safely
            # Using make_interval avoids placing placeholders inside string literals
            where_clauses.append("uae.last_view_date >= NOW() - make_interval(days => %s)")
            params.append(days)
            
            where_sql = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            
            # JOIN برای suggested (match mode too to avoid cross-mode joins)
            join_suggested = (
                "JOIN suggested_attachments sa ON a.id = sa.attachment_id AND sa.mode = a.mode"
                if suggested_only else ""
            )
            
            query = f"""
                SELECT 
                    a.id,
                    a.name,
                    a.code,
                    a.mode,
                    w.name as weapon,
                    wc.name as category,
                    COUNT(CASE WHEN uae.rating = 1 THEN 1 END) as likes,
                    COUNT(CASE WHEN uae.rating = -1 THEN 1 END) as dislikes,
                    COUNT(DISTINCT uae.user_id) as unique_users,
                    SUM(COALESCE(uae.total_views, 0)) as views,
                    SUM(COALESCE(uae.total_clicks, 0)) as total_clicks,
                    (COUNT(CASE WHEN uae.rating = 1 THEN 1 END) - 
                     COUNT(CASE WHEN uae.rating = -1 THEN 1 END)) as net_score
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories wc ON w.category_id = wc.id
                {join_suggested}
                LEFT JOIN user_attachment_engagement uae ON a.id = uae.attachment_id
                {where_sql}
                GROUP BY a.id, a.name, a.code, a.mode, w.name, wc.name
                ORDER BY net_score DESC, views DESC, likes DESC
                LIMIT %s
            """
            
            params.append(limit)
            results = self.execute_query(query, tuple(params), fetch_all=True)
            
            logger.debug(f"✅ Found {len(results)} popular attachments")
            return results
            
        except Exception as e:
            log_exception(logger, e, "get_popular_attachments")
            return []
    
    # ==========================================================================
    # Phase 1: User Management - Day 4
    # ==========================================================================
    
    def is_admin(self, user_id: int) -> bool:
        """بررسی ادمین بودن کاربر - CRITICAL"""
        try:
            query = "SELECT 1 FROM admins WHERE user_id = %s LIMIT 1"
            result = self.execute_query(query, (user_id,), fetch_one=True)
            return result is not None
        except Exception as e:
            log_exception(logger, e, f"is_admin({user_id})")
            return False
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None) -> bool:
        """افزودن کاربر جدید"""
        try:
            query = """
                INSERT INTO users (user_id, username, first_name, last_seen)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, users.username),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    last_seen = NOW()
            """
            self.execute_query(query, (user_id, username, first_name))
            logger.debug(f"✅ User added: {user_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"add_user({user_id})")
            return False
    
    def upsert_user(self, user_id: int, username: str = None,
                   first_name: str = None, last_name: str = None) -> bool:
        """Insert or Update user (idempotent)"""
        try:
            # Note: users table doesn't have last_name column
            query = """
                INSERT INTO users (user_id, username, first_name, last_seen)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    username = COALESCE(EXCLUDED.username, users.username),
                    first_name = COALESCE(EXCLUDED.first_name, users.first_name),
                    last_seen = NOW()
            """
            self.execute_query(query, (user_id, username, first_name))
            logger.debug(f"✅ User upserted: {user_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"upsert_user({user_id})")
            return False
    
    def get_admin(self, user_id: int) -> Optional[Dict]:
        """دریافت اطلاعات ادمین"""
        try:
            query = """
                SELECT a.*, u.username, u.first_name
                FROM admins a
                LEFT JOIN users u ON a.user_id = u.user_id
                WHERE a.user_id = %s
            """
            result = self.execute_query(query, (user_id,), fetch_one=True)
            
            if not result:
                return None
            
            admin = result
            # دریافت نقش‌ها
            q_roles = """
                SELECT r.name, r.display_name, r.icon
                FROM admin_roles ar
                JOIN roles r ON ar.role_id = r.id
                WHERE ar.user_id = %s
                ORDER BY r.name
            """
            roles = self.execute_query(q_roles, (user_id,), fetch_all=True) or []
            admin['roles'] = roles
            return admin
        except Exception as e:
            log_exception(logger, e, f"get_admin({user_id})")
            return None
    
    def get_user_display_name(self, user_id: int) -> str:
        """دریافت نام نمایشی کاربر"""
        try:
            query = """
                SELECT username, first_name
                FROM users
                WHERE user_id = %s
            """
            result = self.execute_query(query, (user_id,), fetch_one=True)
            
            if result:
                username = result.get('username')
                first_name = result.get('first_name')
                
                if username:
                    return f"@{username}"
                elif first_name:
                    return first_name
            
            return f"User_{user_id}"
        except Exception as e:
            logger.debug(f"Could not get display name for {user_id}: {e}")
            return f"User_{user_id}"
    
    def get_all_users(self) -> List[int]:
        """دریافت لیست همه کاربران"""
        try:
            query = "SELECT user_id FROM users WHERE is_subscriber = TRUE"
            results = self.execute_query(query, fetch_all=True)
            return [row['user_id'] for row in results]
        except Exception as e:
            log_exception(logger, e, "get_all_users")
            return []
    
    def get_all_admins(self) -> List[Dict]:
        """دریافت لیست همه ادمین‌ها"""
        try:
            # Pre-check schema for created_at column to avoid exception logs
            exists_row = self.execute_query(
                "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='admins' AND column_name='created_at') AS has_created",
                fetch_one=True,
            )
            has_created = exists_row.get('has_created') if exists_row else False

            if has_created:
                query = """
                    SELECT 
                      a.user_id,
                      COALESCE(a.added_at, a.created_at) AS added_at,
                      a.display_name,
                      u.username,
                      u.first_name,
                      COALESCE(
                        (
                          SELECT json_agg(json_build_object('name', r.name, 'display_name', r.display_name, 'icon', r.icon))
                          FROM user_roles ar 
                          JOIN roles r ON ar.role_id = r.id
                          WHERE ar.user_id = a.user_id
                        ), '[]'::json
                      ) AS roles
                    FROM admins a
                    LEFT JOIN users u ON a.user_id = u.user_id
                    ORDER BY COALESCE(a.added_at, a.created_at) DESC
                """
            else:
                query = """
                    SELECT 
                      a.user_id,
                      a.added_at AS added_at,
                      a.display_name,
                      u.username,
                      u.first_name,
                      COALESCE(
                        (
                          SELECT json_agg(json_build_object('name', r.name, 'display_name', r.display_name, 'icon', r.icon))
                          FROM user_roles ar 
                          JOIN roles r ON ar.role_id = r.id
                          WHERE ar.user_id = a.user_id
                        ), '[]'::json
                      ) AS roles
                    FROM admins a
                    LEFT JOIN users u ON a.user_id = u.user_id
                    ORDER BY a.added_at DESC
                """

            rows = self.execute_query(query, fetch_all=True) or []
            admins: List[Dict] = []
            import json as _json
            for row in rows:
                item = dict(row)
                # Normalize roles to list[dict]
                roles = item.get('roles')
                if isinstance(roles, str):
                    try:
                        roles = _json.loads(roles)
                    except Exception:
                        roles = []
                item['roles'] = roles or []
                admins.append(item)
            return admins
        except Exception as e:
            log_exception(logger, e, "get_all_admins")
            return []
    
    def get_admins_count(self) -> int:
        """تعداد ادمین‌ها"""
        try:
            query = "SELECT COUNT(*) as count FROM admins"
            result = self.execute_query(query, fetch_one=True)
            return result['count'] if result else 0
        except Exception as e:
            log_exception(logger, e, "get_admins_count")
            return 0
    
    # ==========================================================================
    # Phase 1: User Attachments - Day 5
    # ==========================================================================
    
    def add_user_attachment(self, user_id: int, weapon_id: int = None, mode: str = None,
                           category: str = None, custom_weapon_name: str = None,
                           attachment_name: str = None, image_file_id: str = None,
                           description: str = None) -> Optional[int]:
        """افزودن اتچمنت کاربر"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO user_attachments (
                        user_id, weapon_id, mode, category, custom_weapon_name,
                        attachment_name, image_file_id, description, status, submitted_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW())
                    RETURNING id
                """, (user_id, weapon_id, mode, category, custom_weapon_name,
                      attachment_name, image_file_id, description))
                
                result = cursor.fetchone()
                attachment_id = result['id']
                cursor.close()
                
                logger.info(f"✅ User attachment added: ID={attachment_id}")
                return attachment_id
        except Exception as e:
            log_exception(logger, e, "add_user_attachment")
            return None
    
    def get_user_attachment(self, attachment_id: int) -> Optional[Dict]:
        """دریافت اتچمنت کاربر"""
        try:
            query = """
                SELECT ua.*, u.username, u.first_name
                FROM user_attachments ua
                LEFT JOIN users u ON ua.user_id = u.user_id
                WHERE ua.id = %s
            """
            result = self.execute_query(query, (attachment_id,), fetch_one=True)
            
            if result:
                data = dict(result)
                data['weapon_name'] = data.get('custom_weapon_name', 'نامشخص')
                data['category_name'] = data.get('category', 'نامشخص')
                return data
            return None
        except Exception as e:
            log_exception(logger, e, f"get_user_attachment({attachment_id})")
            return None
    
    def get_user_attachments_by_status(self, status: str = 'pending',
                                      limit: int = 50, offset: int = 0) -> List[Dict]:
        """دریافت اتچمنت‌های کاربر بر اساس وضعیت"""
        try:
            query = """
                SELECT ua.*, u.username, u.first_name
                FROM user_attachments ua
                LEFT JOIN users u ON ua.user_id = u.user_id
                WHERE ua.status = %s
                ORDER BY ua.submitted_at DESC
                LIMIT %s OFFSET %s
            """
            results = self.execute_query(query, (status, limit, offset), fetch_all=True)
            return results
        except Exception as e:
            log_exception(logger, e, f"get_user_attachments_by_status({status})")
            return []
    
    def approve_user_attachment(self, attachment_id: int, admin_id: int) -> bool:
        """تایید اتچمنت کاربر"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # دریافت user_id
                cursor.execute("""
                    SELECT user_id FROM user_attachments WHERE id = %s
                """, (attachment_id,))
                
                row = cursor.fetchone()
                if not row:
                    cursor.close()
                    return False
                
                user_id = row['user_id']
                
                # تایید
                cursor.execute("""
                    UPDATE user_attachments
                    SET status = 'approved',
                        approved_at = NOW(),
                        approved_by = %s
                    WHERE id = %s
                """, (admin_id, attachment_id))
                
                # آپدیت آمار
                cursor.execute("""
                    UPDATE user_submission_stats
                    SET approved_submissions = approved_submissions + 1
                    WHERE user_id = %s
                """, (user_id,))
                
                cursor.close()
                logger.info(f"✅ User attachment {attachment_id} approved")
                return True
        except Exception as e:
            log_exception(logger, e, f"approve_user_attachment({attachment_id})")
            return False
    
    def reject_user_attachment(self, attachment_id: int, admin_id: int, reason: str) -> bool:
        """رد اتچمنت کاربر"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # دریافت user_id
                cursor.execute("""
                    SELECT user_id FROM user_attachments WHERE id = %s
                """, (attachment_id,))
                
                row = cursor.fetchone()
                if not row:
                    cursor.close()
                    return False
                
                user_id = row['user_id']
                
                # رد
                cursor.execute("""
                    UPDATE user_attachments
                    SET status = 'rejected',
                        rejected_at = NOW(),
                        rejected_by = %s,
                        rejection_reason = %s
                    WHERE id = %s
                """, (admin_id, reason, attachment_id))
                
                # آپدیت آمار
                cursor.execute("""
                    UPDATE user_submission_stats
                    SET rejected_submissions = rejected_submissions + 1
                    WHERE user_id = %s
                """, (user_id,))
                
                cursor.close()
                logger.info(f"✅ User attachment {attachment_id} rejected")
                return True
        except Exception as e:
            log_exception(logger, e, f"reject_user_attachment({attachment_id})")
            return False
    
    # ==========================================================================
    # Phase 2: Admin Management - Day 1
    # ==========================================================================
    
    def remove_admin(self, user_id: int) -> bool:
        """حذف کامل ادمین (تمام نقش‌هایش)"""
        try:
            query = "DELETE FROM admins WHERE user_id = %s"
            self.execute_query(query, (user_id,))
            logger.info(f"✅ Admin {user_id} and all roles removed (PostgreSQL)")
            return True
        except Exception as e:
            log_exception(logger, e, f"remove_admin({user_id})")
            return False
    
    def assign_role_to_admin(self, user_id: int, role_name: str,
                            username: str = None, first_name: str = None,
                            display_name: str = None, added_by: int = None) -> bool:
        """اختصاص نقش به ادمین"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # دریافت role_id
                cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
                role = cursor.fetchone()
                
                if not role:
                    cursor.close()
                    logger.error(f"❌ Role {role_name} not found")
                    return False
                
                role_id = role.get('id')
                
                # اضافه کردن ادمین اگر وجود ندارد
                # جدول admins حداقل شامل user_id و display_name است؛ سایر فیلدها از جدول users گرفته می‌شوند
                cursor.execute("""
                    INSERT INTO admins (user_id, display_name)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id, display_name))
                
                # به‌روزرسانی display_name اگر ارسال شده
                if display_name:
                    cursor.execute("""
                        UPDATE admins 
                        SET display_name = %s
                        WHERE user_id = %s
                    """, (display_name, user_id))
                
                # اضافه کردن نقش (اگر قبلاً نداشته)
                try:
                    cursor.execute(
                        """
                        INSERT INTO user_roles (user_id, role_id)
                        VALUES (%s, %s)
                        ON CONFLICT (user_id, role_id) DO NOTHING
                        """,
                        (user_id, role_id),
                    )
                except UniqueViolation:
                    # در برخی دیتابیس‌های قدیمی، PK روی ستون id بوده و باعث UniqueViolation می‌شود
                    # در این حالت، بررسی می‌کنیم آیا نقش قبلاً نسبت داده شده است یا خیر
                    cursor.execute(
                        "SELECT 1 FROM user_roles WHERE user_id = %s AND role_id = %s",
                        (user_id, role_id),
                    )
                    if cursor.fetchone() is None:
                        # تلاش برای مهاجرت خودکار: حذف PK قدیمی و تنظیم PK مرکب (user_id, role_id)
                        try:
                            # آیا ستون id وجود دارد؟ اگر بله، طرح‌واره را اصلاح کن
                            cursor.execute(
                                "SELECT 1 FROM information_schema.columns WHERE table_name='user_roles' AND column_name='id'"
                            )
                            if cursor.fetchone():
                                try:
                                    cursor.execute("ALTER TABLE user_roles DROP CONSTRAINT IF EXISTS user_roles_pkey")
                                except Exception:
                                    pass
                                try:
                                    cursor.execute("ALTER TABLE user_roles DROP COLUMN IF EXISTS id")
                                except Exception:
                                    pass
                                try:
                                    cursor.execute("ALTER TABLE user_roles ADD PRIMARY KEY (user_id, role_id)")
                                except Exception:
                                    pass
                                # تلاش مجدد برای درج
                                try:
                                    cursor.execute(
                                        """
                                        INSERT INTO user_roles (user_id, role_id)
                                        VALUES (%s, %s)
                                        ON CONFLICT (user_id, role_id) DO NOTHING
                                        """,
                                        (user_id, role_id),
                                    )
                                except Exception:
                                    # اگر باز هم خطا داد، چشم‌پوشی کن تا جریان UI قطع نشود
                                    pass
                        except Exception:
                            # اگر مهاجرت خودکار شکست خورد، جریان را قطع نکن
                            pass
                
                cursor.close()
                logger.info(f"✅ Admin {user_id} assigned role {role_name} (PostgreSQL)")
                return True
                
        except Exception as e:
            log_exception(logger, e, f"assign_role_to_admin({user_id}, {role_name})")
            return False
    
    def remove_role_from_admin(self, user_id: int, role_name: str) -> bool:
        """حذف یک نقش خاص از ادمین"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # دریافت role_id
                cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
                role = cursor.fetchone()
                
                if not role:
                    cursor.close()
                    logger.error(f"❌ Role {role_name} not found")
                    return False
                
                role_id = role.get('id')
                
                # حذف نقش از admin_roles
                cursor.execute("""
                    DELETE FROM admin_roles 
                    WHERE user_id = %s AND role_id = %s
                """, (user_id, role_id))
                
                cursor.close()
                logger.info(f"✅ Role {role_name} removed from admin {user_id} (PostgreSQL)")
                return True
                
        except Exception as e:
            log_exception(logger, e, f"remove_role_from_admin({user_id}, {role_name})")
            return False
    
    def get_admin_roles(self, user_id: int) -> List[str]:
        """دریافت لیست نام نقش‌های یک ادمین"""
        try:
            query = """
                SELECT r.name
                FROM user_roles ar
                JOIN roles r ON ar.role_id = r.id
                WHERE ar.user_id = %s
                ORDER BY r.name
            """
            results = self.execute_query(query, (user_id,), fetch_all=True)
            return [row['name'] for row in results]
        except Exception as e:
            log_exception(logger, e, f"get_admin_roles({user_id})")
            return []
    
    # ==========================================================================
    # Phase 2: RBAC & Ban System - Day 2
    # ==========================================================================
    
    def get_all_roles(self) -> List[Dict]:
        """دریافت تمام نقش‌ها با permissions"""
        try:
            query_roles = """
                SELECT id, name, display_name, description, icon
                FROM roles
                ORDER BY name
            """
            roles = self.execute_query(query_roles, fetch_all=True)
            
            result = []
            for role in roles:
                # دریافت permissions هر نقش
                query_perms = """
                    SELECT permission
                    FROM role_permissions
                    WHERE role_id = %s
                """
                permissions = self.execute_query(query_perms, (role['id'],), fetch_all=True)
                
                result.append({
                    'name': role['name'],
                    'display_name': role['display_name'],
                    'description': role['description'],
                    'icon': role['icon'],
                    'permissions': [p['permission'] for p in permissions]
                })
            
            return result
            
        except Exception as e:
            log_exception(logger, e, "get_all_roles")
            return []
    
    def get_role(self, role_name: str) -> Optional[Dict]:
        """دریافت اطلاعات یک نقش"""
        try:
            query_role = """
                SELECT id, name, display_name, description, icon
                FROM roles
                WHERE name = %s
            """
            role = self.execute_query(query_role, (role_name,), fetch_one=True)
            
            if not role:
                return None
            
            # دریافت permissions
            query_perms = """
                SELECT permission
                FROM role_permissions
                WHERE role_id = %s
            """
            permissions = self.execute_query(query_perms, (role['id'],), fetch_all=True)
            
            return {
                'name': role['name'],
                'display_name': role['display_name'],
                'description': role['description'],
                'icon': role['icon'],
                'permissions': [p['permission'] for p in permissions]
            }
            
        except Exception as e:
            log_exception(logger, e, f"get_role({role_name})")
            return None
    
    def ban_user_from_submissions(self, user_id: int, reason: str, 
                                  banned_by: int = None) -> bool:
        """محروم کردن کاربر از ارسال اتچمنت"""
        try:
            query = """
                UPDATE user_submission_stats
                SET is_banned = TRUE,
                    banned_at = NOW(),
                    banned_reason = %s
                WHERE user_id = %s
            """
            self.execute_query(query, (reason, user_id))
            logger.warning(f"⚠️ User {user_id} banned from submissions: {reason}")
            return True
        except Exception as e:
            log_exception(logger, e, f"ban_user_from_submissions({user_id})")
            return False
    
    def unban_user_from_submissions(self, user_id: int) -> bool:
        """رفع محرومیت کاربر"""
        try:
            query = """
                UPDATE user_submission_stats
                SET is_banned = FALSE,
                    banned_at = NULL,
                    banned_until = NULL,
                    banned_reason = NULL,
                    strike_count = 0
                WHERE user_id = %s
            """
            self.execute_query(query, (user_id,))
            logger.info(f"✅ User {user_id} unbanned from submissions")
            return True
        except Exception as e:
            log_exception(logger, e, f"unban_user_from_submissions({user_id})")
            return False
    
    # ==========================================================================
    # Phase 2: Channel Management - Day 3
    # ==========================================================================
    
    def get_required_channels(self) -> List[Dict]:
        """دریافت کانال‌های اجباری فعال (بر اساس priority)"""
        try:
            query = """
                SELECT channel_id, title, url, priority
                FROM required_channels
                WHERE is_active = TRUE
                ORDER BY priority ASC, channel_id ASC
            """
            results = self.execute_query(query, fetch_all=True)
            return results
        except Exception as e:
            log_exception(logger, e, "get_required_channels")
            return []
    
    def add_required_channel(self, channel_id: str, title: str, url: str) -> bool:
        """اضافه کردن کانال اجباری"""
        try:
            query = """
                INSERT INTO required_channels (channel_id, title, url)
                VALUES (%s, %s, %s)
                ON CONFLICT (channel_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    url = EXCLUDED.url,
                    is_active = TRUE
            """
            self.execute_query(query, (channel_id, title, url))
            logger.info(f"✅ Required channel added: {channel_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"add_required_channel({channel_id})")
            return False
    
    def remove_required_channel(self, channel_id: str) -> bool:
        """حذف کانال اجباری (soft delete)"""
        try:
            query = """
                UPDATE required_channels 
                SET is_active = FALSE 
                WHERE channel_id = %s
            """
            self.execute_query(query, (channel_id,))
            logger.info(f"✅ Required channel removed: {channel_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"remove_required_channel({channel_id})")
            return False
    
    def update_required_channel(self, channel_id: str, new_title: str = None,
                               new_url: str = None) -> bool:
        """ویرایش کانال اجباری"""
        try:
            updates = []
            params = []
            
            if new_title is not None:
                updates.append("title = %s")
                params.append(new_title)
            
            if new_url is not None:
                updates.append("url = %s")
                params.append(new_url)
            
            if not updates:
                return True  # Nothing to update
            
            params.append(channel_id)
            query = f"""
                UPDATE required_channels 
                SET {', '.join(updates)}
                WHERE channel_id = %s
            """
            
            self.execute_query(query, tuple(params))
            logger.info(f"✅ Required channel updated: {channel_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"update_required_channel({channel_id})")
            return False
    
    def get_channel_by_id(self, channel_id: str) -> Optional[Dict]:
        """دریافت اطلاعات یک کانال (حتی اگر غیرفعال باشد)"""
        try:
            query = """
                SELECT channel_id, title, url, priority, is_active
                FROM required_channels
                WHERE channel_id = %s
            """
            return self.execute_query(query, (channel_id,), fetch_one=True)
        except Exception as e:
            log_exception(logger, e, f"get_channel_by_id({channel_id})")
            return None

    def toggle_channel_status(self, channel_id: str) -> bool:
        """تغییر وضعیت فعال/غیرفعال بودن کانال"""
        try:
            query = """
                UPDATE required_channels
                SET is_active = NOT is_active
                WHERE channel_id = %s
            """
            self.execute_query(query, (channel_id,))
            logger.info(f"✅ Channel status toggled: {channel_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"toggle_channel_status({channel_id})")
            return False

    def clear_required_channels(self) -> bool:
        """غیرفعال کردن تمام کانال‌های اجباری"""
        try:
            query = "UPDATE required_channels SET is_active = FALSE"
            self.execute_query(query)
            logger.info("✅ All required channels cleared (set inactive)")
            return True
        except Exception as e:
            log_exception(logger, e, "clear_required_channels")
            return False
    
    # ==========================================================================
    # Phase 2: Channel Priority - Day 4
    # ==========================================================================
    
    def update_channel_priority(self, channel_id: str, new_priority: int) -> bool:
        """تغییر اولویت کانال"""
        try:
            query = """
                UPDATE required_channels 
                SET priority = %s
                WHERE channel_id = %s
            """
            self.execute_query(query, (new_priority, channel_id))
            logger.info(f"✅ Channel priority updated: {channel_id} -> {new_priority}")
            return True
        except Exception as e:
            log_exception(logger, e, f"update_channel_priority({channel_id})")
            return False
    
    def move_channel_up(self, channel_id: str) -> bool:
        """جابجایی کانال به بالا (کاهش priority)"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # دریافت priority فعلی
                cursor.execute("""
                    SELECT priority FROM required_channels WHERE channel_id = %s
                """, (channel_id,))
                current = cursor.fetchone()
                
                if not current:
                    cursor.close()
                    return False
                
                current_priority = current[0]
                
                # پیدا کردن کانال بالاتر
                cursor.execute("""
                    SELECT channel_id, priority 
                    FROM required_channels 
                    WHERE priority < %s AND is_active = TRUE
                    ORDER BY priority DESC 
                    LIMIT 1
                """, (current_priority,))
                previous = cursor.fetchone()
                
                if not previous:
                    cursor.close()
                    return False  # Already at top
                
                # Atomic swap priorities
                prev_channel_id = previous[0]
                prev_priority = previous[1]
                
                cursor.execute("""
                    UPDATE required_channels SET priority = %s WHERE channel_id = %s
                """, (prev_priority, channel_id))
                
                cursor.execute("""
                    UPDATE required_channels SET priority = %s WHERE channel_id = %s
                """, (current_priority, prev_channel_id))
                
                cursor.close()
                logger.info(f"✅ Channel moved up: {channel_id}")
                return True
        except Exception as e:
            log_exception(logger, e, f"move_channel_up({channel_id})")
            return False
    
    def move_channel_down(self, channel_id: str) -> bool:
        """جابجایی کانال به پایین (افزایش priority)"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # دریافت priority فعلی
                cursor.execute("""
                    SELECT priority FROM required_channels WHERE channel_id = %s
                """, (channel_id,))
                current = cursor.fetchone()
                
                if not current:
                    cursor.close()
                    return False
                
                current_priority = current[0]
                
                # پیدا کردن کانال پایین‌تر
                cursor.execute("""
                    SELECT channel_id, priority 
                    FROM required_channels 
                    WHERE priority > %s AND is_active = TRUE
                    ORDER BY priority ASC 
                    LIMIT 1
                """, (current_priority,))
                next_ch = cursor.fetchone()
                
                if not next_ch:
                    cursor.close()
                    return False  # Already at bottom
                
                # Atomic swap priorities
                next_channel_id = next_ch[0]
                next_priority = next_ch[1]
                
                cursor.execute("""
                    UPDATE required_channels SET priority = %s WHERE channel_id = %s
                """, (next_priority, channel_id))
                
                cursor.execute("""
                    UPDATE required_channels SET priority = %s WHERE channel_id = %s
                """, (current_priority, next_channel_id))
                
                cursor.close()
                logger.info(f"✅ Channel moved down: {channel_id}")
                return True
        except Exception as e:
            log_exception(logger, e, f"move_channel_down({channel_id})")
            return False
    
    # ==========================================================================
    # Phase 2: Search & Analytics - Day 5 (Final)
    # ==========================================================================
    
    def search_attachments_like(self, query: str, limit: int = 30) -> List[Dict]:
        """جستجوی ساده با LIKE (fallback)"""
        try:
            # نرمال‌سازی query
            normalized_query = '%' + ''.join(c.lower() for c in query if c.isalnum()) + '%'
            
            query_sql = """
                SELECT c.name as category, w.name as weapon, a.mode,
                       a.code, a.name as att_name, a.image_file_id as image,
                       a.is_top, a.is_season_top
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE LOWER(REPLACE(REPLACE(a.name, ' ', ''), '-', '')) LIKE %s
                   OR LOWER(REPLACE(REPLACE(w.name, ' ', ''), '-', '')) LIKE %s
                   OR LOWER(a.code) LIKE %s
                ORDER BY a.is_season_top DESC, a.is_top DESC
                LIMIT %s
            """
            
            results = self.execute_query(
                query_sql, 
                (normalized_query, normalized_query, normalized_query, limit),
                fetch_all=True
            )
            
            items = []
            for row in results:
                items.append({
                    'category': row['category'],
                    'weapon': row['weapon'],
                    'mode': row['mode'],
                    'attachment': {
                        'code': row['code'],
                        'name': row['att_name'],
                        'image': row['image'],
                        'is_top': row.get('is_top', False),
                        'is_season_top': row.get('is_season_top', False)
                    }
                })
            
            logger.debug(f"LIKE search for '{query}' returned {len(items)} results")
            return items
            
        except Exception as e:
            log_exception(logger, e, f"search_attachments_like({query})")
            return []
    
    def search_attachments_fts(self, query: str, limit: int = 30) -> List[Dict]:
        """جستجوی پیشرفته با pg_trgm (PostgreSQL)"""
        try:
            # برای کوئری‌های بسیار کوتاه یا صرفاً عددی، مستقیماً از LIKE استفاده کن
            q = (query or '').strip()
            if not q:
                return []
            if len(q) < 3 or q.isdigit():
                return self.search_attachments_like(query, limit)

            # استفاده از pg_trgm برای similarity search
            query_sql = """
                SELECT 
                    c.name as category,
                    w.name as weapon,
                    a.mode,
                    a.code,
                    a.name as att_name,
                    a.image_file_id as image,
                    a.is_top,
                    a.is_season_top,
                    -- محاسبه امتیاز شباهت
                    GREATEST(
                        similarity(a.name, %s),
                        similarity(w.name, %s),
                        similarity(a.code, %s)
                    ) as score
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE 
                    a.name %% %s  -- pg_trgm operator
                    OR w.name %% %s
                    OR a.code %% %s
                    -- همچنین برای پوشش کامل، جستجوی ILIKE هم اضافه می‌کنیم
                    OR a.code ILIKE %s
                    OR a.name ILIKE %s
                    OR w.name ILIKE %s
                ORDER BY score DESC, a.is_season_top DESC, a.is_top DESC
                LIMIT %s
            """
            like_pattern = f"%{q}%"
            results = self.execute_query(
                query_sql,
                (q, q, q, q, q, q, like_pattern, like_pattern, like_pattern, limit),
                fetch_all=True
            )
            
            items = []
            for row in results:
                items.append({
                    'category': row['category'],
                    'weapon': row['weapon'],
                    'mode': row['mode'],
                    'attachment': {
                        'code': row['code'],
                        'name': row['att_name'],
                        'image': row['image'],
                        'is_top': row.get('is_top', False),
                        'is_season_top': row.get('is_season_top', False)
                    }
                })
            
            logger.debug(f"FTS search for '{query}' returned {len(items)} results")
            # اگر نتیجه‌ای نبود، به LIKE fallback کن
            if not items:
                return self.search_attachments_like(query, limit)
            return items
            
        except Exception as e:
            # Fallback to LIKE if pg_trgm not available
            logger.warning(f"FTS search failed, falling back to LIKE: {e}")
            return self.search_attachments_like(query, limit)
    
    def search_attachments(self, query: str) -> List[Dict]:
        """جستجوی هوشمند (wrapper)"""
        try:
            # استفاده از FTS
            return self.search_attachments_fts(query, limit=30)
        except Exception as e:
            log_exception(logger, e, f"search_attachments({query})")
            return []
    
    def track_search(self, user_id: int, query: str, results_count: int, 
                    execution_time_ms: float) -> bool:
        """ثبت جستجو برای Analytics"""
        try:
            query_normalized = query.strip().lower()
            if not query_normalized or len(query_normalized) < 2:
                return False
            with self.transaction() as conn:
                cursor = conn.cursor()
                # ثبت در تاریخچه
                cursor.execute("""
                    INSERT INTO search_history (user_id, query, results_count, execution_time_ms)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, query_normalized, results_count, execution_time_ms))
                # به‌روزرسانی popular searches
                cursor.execute("""
                    INSERT INTO popular_searches (query, search_count, last_searched)
                    VALUES (%s, 1, NOW())
                    ON CONFLICT(query) DO UPDATE SET
                        search_count = popular_searches.search_count + 1,
                        last_searched = NOW()
                """, (query_normalized,))
                cursor.close()
            logger.debug(f"Search tracked: user={user_id}, query='{query_normalized}'")
            return True
        except Exception as e:
            logger.warning(f"Error tracking search: {e}")
            return False
    
    def get_popular_searches(self, limit: int = 5) -> List[str]:
        """دریافت محبوب‌ترین جستجوها"""
        try:
            query = """
                SELECT query
                FROM popular_searches
                ORDER BY search_count DESC, last_searched DESC
                LIMIT %s
            """
            results = self.execute_query(query, (limit,), fetch_all=True)
            return [r['query'] for r in results]
        except Exception as e:
            log_exception(logger, e, "get_popular_searches")
            return []
    
    def get_search_analytics(self, days: int = 30) -> Dict:
        """دریافت آمار جستجو"""
        try:
            # آمار کلی
            query_stats = """
                SELECT 
                    COUNT(*) as total_searches,
                    COUNT(DISTINCT user_id) as unique_users,
                    AVG(results_count) as avg_results,
                    AVG(execution_time_ms) as avg_time_ms,
                    SUM(CASE WHEN results_count = 0 THEN 1 ELSE 0 END) as zero_results
                FROM search_history
                WHERE created_at >= NOW() - make_interval(days => %s)
            """
            stats = self.execute_query(query_stats, (days,), fetch_one=True)
            
            # محبوب‌ترین جستجوها
            query_top = """
                SELECT query, COUNT(*) as count
                FROM search_history
                WHERE created_at >= NOW() - make_interval(days => %s)
                GROUP BY query
                ORDER BY count DESC
                LIMIT 10
            """
            top_queries = self.execute_query(query_top, (days,), fetch_all=True)
            
            # جستجوهای بدون نتیجه
            query_failed = """
                SELECT query, COUNT(*) as count
                FROM search_history
                WHERE results_count = 0
                  AND created_at >= NOW() - make_interval(days => %s)
                GROUP BY query
                ORDER BY count DESC
                LIMIT 10
            """
            failed_queries = self.execute_query(query_failed, (days,), fetch_all=True)
            
            total = stats['total_searches'] or 1
            zero_rate = (stats['zero_results'] / total) * 100 if total > 0 else 0
            
            return {
                'total_searches': stats['total_searches'] or 0,
                'unique_users': stats['unique_users'] or 0,
                'avg_results': round(stats['avg_results'] or 0, 1),
                'avg_time_ms': round(stats['avg_time_ms'] or 0, 1),
                'zero_results': stats['zero_results'] or 0,
                'zero_rate': round(zero_rate, 1),
                'top_queries': [{'query': q['query'], 'count': q['count']} for q in top_queries],
                'failed_queries': [{'query': q['query'], 'count': q['count']} for q in failed_queries]
            }
            
        except Exception as e:
            log_exception(logger, e, "get_search_analytics")
            return {
                'total_searches': 0,
                'unique_users': 0,
                'avg_results': 0,
                'avg_time_ms': 0,
                'zero_results': 0,
                'zero_rate': 0,
                'top_queries': [],
                'failed_queries': []
            }
    
    def get_attachment_stats(self, attachment_id: int, period: str = 'all') -> Dict:
        """دریافت آمار بازخورد اتچمنت"""
        try:
            # تعیین فیلتر زمانی
            date_filter = ""
            if period == 'week':
                date_filter = "AND last_view_date >= NOW() - INTERVAL '7 days'"
            elif period == 'month':
                date_filter = "AND last_view_date >= NOW() - INTERVAL '30 days'"
            elif period == 'year':
                date_filter = "AND last_view_date >= NOW() - INTERVAL '365 days'"
            
            # آمار رأی‌ها
            query_votes = f"""
                SELECT 
                    SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as likes,
                    SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) as dislikes,
                    COUNT(CASE WHEN rating IS NOT NULL THEN 1 END) as total_votes,
                    SUM(COALESCE(total_views, 0)) as total_views,
                    SUM(COALESCE(total_clicks, 0)) as total_clicks,
                    COUNT(DISTINCT user_id) as unique_users
                FROM user_attachment_engagement
                WHERE attachment_id = %s {date_filter}
            """
            
            vote_stats = self.execute_query(query_votes, (attachment_id,), fetch_one=True)
            
            likes = vote_stats['likes'] or 0
            dislikes = vote_stats['dislikes'] or 0
            total_votes = vote_stats['total_votes'] or 0
            
            # محاسبه نسبت‌ها
            like_ratio = (likes / total_votes * 100) if total_votes > 0 else 0
            dislike_ratio = (dislikes / total_votes * 100) if total_votes > 0 else 0
            
            return {
                'like_count': likes,
                'dislike_count': dislikes,
                'total_votes': total_votes,
                'like_ratio': round(like_ratio, 1),
                'dislike_ratio': round(dislike_ratio, 1),
                'net_score': likes - dislikes,
                'total_views': vote_stats['total_views'] or 0,
                'total_clicks': vote_stats['total_clicks'] or 0,
                'unique_users': vote_stats['unique_users'] or 0,
                'period': period
            }
            
        except Exception as e:
            log_exception(logger, e, f"get_attachment_stats({attachment_id})")
            return {
                'like_count': 0,
                'dislike_count': 0,
                'total_votes': 0,
                'like_ratio': 0,
                'dislike_ratio': 0,
                'net_score': 0,
                'total_views': 0,
                'total_clicks': 0,
                'unique_users': 0,
                'period': period
            }
    
    # ==========================================================================
    # Phase 3: Guide Management - Day 1
    # ==========================================================================
    
    def get_guides(self, mode: str = "br") -> Dict[str, Dict]:
        """دریافت راهنماها"""
        try:
            guides = {}
            
            # دریافت راهنماها
            query_guides = """
                SELECT id, key, name, code
                FROM guides
                WHERE mode = %s
            """
            result = self.execute_query(query_guides, (mode,), fetch_all=True)
            
            for guide in result:
                guide_dict = {
                    'name': guide['name'],
                    'code': guide['code'] or '',
                    'photos': [],
                    'videos': []
                }
                
                # دریافت رسانه‌ها
                query_media = """
                    SELECT media_type, file_id
                    FROM guide_media
                    WHERE guide_id = %s
                    ORDER BY order_index, id
                """
                media = self.execute_query(query_media, (guide['id'],), fetch_all=True)
                
                for m in media:
                    if m['media_type'] == 'photo':
                        guide_dict['photos'].append(m['file_id'])
                    else:
                        guide_dict['videos'].append(m['file_id'])
                
                guides[guide['key']] = guide_dict
            
            # اگر راهنماهای پیش‌فرض وجود ندارند، آنها را ایجاد کن
            default_guides = ['basic', 'sens', 'hud']
            for key in default_guides:
                if key not in guides:
                    guides[key] = {
                        'name': key.title(),
                        'code': '',
                        'photos': [],
                        'videos': []
                    }
            
            return guides
        except Exception as e:
            log_exception(logger, e, f"get_guides({mode})")
            return {}
    
    def get_guide(self, key: str, mode: str = "br") -> Dict:
        """دریافت یک راهنمای خاص"""
        try:
            # دریافت راهنما
            query_guide = """
                SELECT id, key, name, code
                FROM guides
                WHERE key = %s AND mode = %s
            """
            guide = self.execute_query(query_guide, (key, mode), fetch_one=True)
            
            guide_dict = {
                'name': key,
                'code': '',
                'photos': [],
                'videos': []
            }
            
            if guide:
                guide_dict['name'] = guide['name']
                guide_dict['code'] = guide['code'] or ''
                
                # دریافت رسانه‌ها
                query_media = """
                    SELECT media_type, file_id
                    FROM guide_media
                    WHERE guide_id = %s
                    ORDER BY order_index, id
                """
                media = self.execute_query(query_media, (guide['id'],), fetch_all=True)
                
                for m in media:
                    if m['media_type'] == 'photo':
                        guide_dict['photos'].append(m['file_id'])
                    else:
                        guide_dict['videos'].append(m['file_id'])
            
            return guide_dict
        except Exception as e:
            log_exception(logger, e, f"get_guide({key}, {mode})")
            return {'name': key, 'code': '', 'photos': [], 'videos': []}
    
    def set_guide_name(self, key: str, name: str, mode: str = "br") -> bool:
        """تنظیم نام راهنما"""
        try:
            query = """
                INSERT INTO guides (key, mode, name)
                VALUES (%s, %s, %s)
                ON CONFLICT (key, mode) DO UPDATE SET
                    name = EXCLUDED.name
            """
            self.execute_query(query, (key, mode, name))
            logger.info(f"✅ Guide name set: {key} -> {name}")
            return True
        except Exception as e:
            log_exception(logger, e, f"set_guide_name({key})")
            return False

    def set_guide_code(self, key: str, code: str, mode: str = "br") -> bool:
        """تنظیم کد راهنما (Sens/HUD)"""
        try:
            query = """
                INSERT INTO guides (key, mode, name, code)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (key, mode) DO UPDATE SET
                    code = EXCLUDED.code
            """
            # اگر قبلاً name تعیین نشده باشد، به صورت پیش‌فرض Title-case می‌گذاریم
            self.execute_query(query, (key, mode, key.title(), code))
            logger.info(f"✅ Guide code set: {key} ({mode})")
            return True
        except Exception as e:
            log_exception(logger, e, f"set_guide_code({key})")
            return False

    def get_guide_code(self, key: str, mode: str = "br") -> str:
        """دریافت کد راهنما"""
        try:
            query = "SELECT code FROM guides WHERE key = %s AND mode = %s"
            result = self.execute_query(query, (key, mode), fetch_one=True)
            return (result.get('code') if result else '') or ''
        except Exception as e:
            log_exception(logger, e, f"get_guide_code({key})")
            return ''

    def clear_guide_code(self, key: str, mode: str = "br") -> bool:
        """حذف کد راهنما (تنظیم به NULL)"""
        try:
            query = "UPDATE guides SET code = NULL WHERE key = %s AND mode = %s"
            self.execute_query(query, (key, mode))
            logger.info(f"✅ Guide code cleared: {key} ({mode})")
            return True
        except Exception as e:
            log_exception(logger, e, f"clear_guide_code({key})")
            return False
    
    def add_guide_photo(self, key: str, file_id: str, mode: str = "br") -> bool:
        """افزودن عکس به راهنما"""
        return self._add_guide_media(key, file_id, 'photo', mode)
    
    def add_guide_video(self, key: str, file_id: str, mode: str = "br") -> bool:
        """افزودن ویدیو به راهنما"""
        return self._add_guide_media(key, file_id, 'video', mode)
    
    def _add_guide_media(self, key: str, file_id: str, media_type: str, mode: str) -> bool:
        """افزودن رسانه به راهنما"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # ابتدا مطمئن شو که guide وجود دارد
                cursor.execute("""
                    INSERT INTO guides (key, mode, name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (key, mode) DO NOTHING
                """, (key, mode, key.title()))
                
                # دریافت guide_id
                cursor.execute("""
                    SELECT id FROM guides WHERE key = %s AND mode = %s
                """, (key, mode))
                result = cursor.fetchone()
                
                if result:
                    guide_id = result['id']
                    
                    # دریافت آخرین order_index
                    cursor.execute("""
                        SELECT COALESCE(MAX(order_index), -1) as max_order
                        FROM guide_media
                        WHERE guide_id = %s
                    """, (guide_id,))
                    result = cursor.fetchone()
                    max_order = result['max_order']
                    
                    # اضافه کردن media
                    cursor.execute("""
                        INSERT INTO guide_media (guide_id, media_type, file_id, order_index)
                        VALUES (%s, %s, %s, %s)
                    """, (guide_id, media_type, file_id, max_order + 1))
                    
                    cursor.close()
                    logger.info(f"✅ Guide media added: {key} ({media_type})")
                    return True
                    
                cursor.close()
                return False
        except Exception as e:
            log_exception(logger, e, f"_add_guide_media({key}, {media_type})")
            return False
    
    # ==========================================================================
    # Phase 3: Weapon Management - Day 2
    # ==========================================================================
    
    def get_weapon_by_name(self, category: str, weapon_name: str) -> dict:
        """دریافت اطلاعات سلاح بر اساس نام و دسته"""
        try:
            query = """
                SELECT w.* 
                FROM weapons w
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE c.name = %s AND w.name = %s
            """
            result = self.execute_query(query, (category, weapon_name), fetch_one=True)
            return dict(result) if result else None
        except Exception as e:
            log_exception(logger, e, f"get_weapon_by_name({category}, {weapon_name})")
            return None
    
    def get_weapon_info(self, category: str, weapon_name: str) -> dict:
        """دریافت اطلاعات کامل یک سلاح"""
        try:
            # دریافت weapon_id
            query_weapon = """
                SELECT w.id, w.is_active 
                FROM weapons w
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE c.name = %s AND w.name = %s
            """
            result = self.execute_query(query_weapon, (category, weapon_name), fetch_one=True)
            
            if not result:
                return {'br': {'attachment_count': 0, 'top_count': 0}, 
                        'mp': {'attachment_count': 0, 'top_count': 0},
                        'is_active': True}
            
            weapon_id = result['id']
            is_active = result.get('is_active', True)
            info = {'is_active': is_active}
            
            for mode in ['br', 'mp']:
                query_counts = """
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN is_top = TRUE THEN 1 ELSE 0 END) as top_count
                    FROM attachments
                    WHERE weapon_id = %s AND mode = %s
                """
                counts = self.execute_query(query_counts, (weapon_id, mode), fetch_one=True)
                
                info[mode] = {
                    'attachment_count': counts['total'] or 0,
                    'top_count': counts['top_count'] or 0
                }
            
            return info
            
        except Exception as e:
            log_exception(logger, e, f"get_weapon_info({category}, {weapon_name})")
            return {'br': {'attachment_count': 0, 'top_count': 0}, 
                    'mp': {'attachment_count': 0, 'top_count': 0},
                    'is_active': True}
    
    def delete_weapon(self, category: str, weapon_name: str, mode: str = None) -> bool:
        """حذف سلاح یا اتچمنت‌های یک mode خاص"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # دریافت weapon_id
                cursor.execute("""
                    SELECT w.id 
                    FROM weapons w
                    JOIN weapon_categories c ON w.category_id = c.id
                    WHERE c.name = %s AND w.name = %s
                """, (category, weapon_name))
                result = cursor.fetchone()
                
                if not result:
                    cursor.close()
                    return False
                
                weapon_id = result['id']
                
                # اگر mode مشخص نشده، کل سلاح را حذف کن
                # اگر mode مشخص نشده، حذف کامل ممنوع است
                if mode is None:
                    # cursor.execute("DELETE FROM weapons WHERE id = %s", (weapon_id,))
                    cursor.close()
                    logger.warning(f"⚠️ Weapon deletion attempted but blocked: {category}/{weapon_name}")
                    return False
                
                # اگر mode مشخص شده، فقط اتچمنت‌های آن mode را حذف کن
                cursor.execute("""
                    DELETE FROM attachments 
                    WHERE weapon_id = %s AND mode = %s
                """, (weapon_id, mode))
                
                cursor.close()
                logger.info(f"✅ Weapon attachments deleted: {category}/{weapon_name} ({mode})")
                return True
                
        except Exception as e:
            log_exception(logger, e, f"delete_weapon({category}, {weapon_name})")
            return False

    def toggle_weapon_status(self, category: str, weapon_name: str) -> bool:
        """تغییر وضعیت فعال/غیرفعال بودن سلاح"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE weapons w
                    SET is_active = NOT COALESCE(w.is_active, TRUE), updated_at = NOW()
                    FROM weapon_categories c
                    WHERE w.category_id = c.id AND c.name = %s AND w.name = %s
                    RETURNING w.is_active
                """, (category, weapon_name))
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    new_status = result['is_active']
                    logger.info(f"✅ Weapon status toggled: {category}/{weapon_name} -> {new_status}")
                    return True
                return False
        except Exception as e:
            log_exception(logger, e, f"toggle_weapon_status({category}, {weapon_name})")
            return False
    
    @cached('db.get_statistics', ttl=180)
    def get_statistics(self) -> Dict:
        """دریافت آمار کامل و تفصیلی دیتابیس"""
        try:
            stats = {
                'total_weapons': 0,
                'total_attachments': 0,
                'total_attachments_br': 0,
                'total_attachments_mp': 0,
                'total_top_attachments': 0,
                'total_season_attachments': 0,
                'total_guides': 0,
                'total_guides_br': 0,
                'total_guides_mp': 0,
                'total_channels': 0,
                'total_admins': 0,
                'categories': {},
                'weapons_with_attachments': 0,
                'weapons_without_attachments': 0
            }
            
            # آمار کلی
            stats['total_weapons'] = self.execute_query("SELECT COUNT(*) as count FROM weapons", fetch_one=True)['count']
            stats['total_attachments'] = self.execute_query("SELECT COUNT(*) as count FROM attachments", fetch_one=True)['count']
            stats['total_attachments_br'] = self.execute_query("SELECT COUNT(*) as count FROM attachments WHERE mode = 'br'", fetch_one=True)['count']
            stats['total_attachments_mp'] = self.execute_query("SELECT COUNT(*) as count FROM attachments WHERE mode = 'mp'", fetch_one=True)['count']
            stats['total_top_attachments'] = self.execute_query("SELECT COUNT(*) as count FROM attachments WHERE is_top = TRUE", fetch_one=True)['count']
            stats['total_season_attachments'] = self.execute_query("SELECT COUNT(*) as count FROM attachments WHERE is_season_top = TRUE", fetch_one=True)['count']
            
            # سلاح‌های دارای/بدون اتچمنت
            with_att = self.execute_query("SELECT COUNT(DISTINCT weapon_id) as count FROM attachments", fetch_one=True)['count']
            stats['weapons_with_attachments'] = with_att
            stats['weapons_without_attachments'] = stats['total_weapons'] - with_att
            
            # آمار راهنماها
            stats['total_guides'] = self.execute_query("SELECT COUNT(*) as count FROM guides", fetch_one=True)['count']
            stats['total_guides_br'] = self.execute_query("SELECT COUNT(*) as count FROM guides WHERE mode = 'br'", fetch_one=True)['count']
            stats['total_guides_mp'] = self.execute_query("SELECT COUNT(*) as count FROM guides WHERE mode = 'mp'", fetch_one=True)['count']
            
            # آمار کانال‌ها و ادمین‌ها
            stats['total_channels'] = self.execute_query("SELECT COUNT(*) as count FROM required_channels WHERE is_active = TRUE", fetch_one=True)['count']
            stats['total_admins'] = self.execute_query("SELECT COUNT(DISTINCT user_id) as count FROM admin_roles", fetch_one=True)['count'] or 0
            
            # آمار تفکیکی به ازای هر دسته
            category_order = ['assault_rifle', 'smg', 'lmg', 'sniper', 'marksman', 'shotgun', 'pistol', 'launcher']
            categories = self.execute_query("SELECT id, name FROM weapon_categories", fetch_all=True)
            cat_dict = {cat['name']: cat for cat in categories}
            
            for cat_name in category_order:
                if cat_name not in cat_dict:
                    continue
                    
                cat = cat_dict[cat_name]
                cat_id = cat['id']
                
                weapon_count = self.execute_query("SELECT COUNT(*) as count FROM weapons WHERE category_id = %s", (cat_id,), fetch_one=True)['count']
                att_count = self.execute_query("SELECT COUNT(*) as count FROM attachments a JOIN weapons w ON a.weapon_id = w.id WHERE w.category_id = %s", (cat_id,), fetch_one=True)['count']
                br_count = self.execute_query("SELECT COUNT(*) as count FROM attachments a JOIN weapons w ON a.weapon_id = w.id WHERE w.category_id = %s AND a.mode = 'br'", (cat_id,), fetch_one=True)['count']
                mp_count = self.execute_query("SELECT COUNT(*) as count FROM attachments a JOIN weapons w ON a.weapon_id = w.id WHERE w.category_id = %s AND a.mode = 'mp'", (cat_id,), fetch_one=True)['count']
                top_count = self.execute_query("SELECT COUNT(*) as count FROM attachments a JOIN weapons w ON a.weapon_id = w.id WHERE w.category_id = %s AND a.is_top = TRUE", (cat_id,), fetch_one=True)['count']
                weapons_with = self.execute_query("SELECT COUNT(DISTINCT w.id) as count FROM weapons w JOIN attachments a ON a.weapon_id = w.id WHERE w.category_id = %s", (cat_id,), fetch_one=True)['count']
                
                category_display = WEAPON_CATEGORIES.get(cat_name, cat_name)
                stats['categories'][cat_name] = {
                    'display_name': category_display,
                    'weapons': weapon_count,
                    'attachments': att_count,
                    'attachments_br': br_count,
                    'attachments_mp': mp_count,
                    'top_attachments': top_count,
                    'weapons_with_attachments': weapons_with,
                    'completion_rate': round((weapons_with / weapon_count * 100) if weapon_count > 0 else 0, 1)
                }
            
            return stats
            
        except Exception as e:
            log_exception(logger, e, "get_statistics")
            return {}
    
    # ==========================================================================
    # Phase 3: Blacklist + Settings + Preferences + Stats - Day 3 (Final)
    # ==========================================================================
    
    def add_blacklisted_word(self, word: str, category: str = 'profanity',
                            severity: int = 1, admin_id: int = None) -> bool:
        """افزودن کلمه ممنوعه"""
        try:
            query = """
                INSERT INTO blacklisted_words (word, category, severity, added_by)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (word) DO NOTHING
            """
            self.execute_query(query, (word.lower(), category, severity, admin_id))
            logger.info(f"✅ Blacklisted word added: '{word}' (severity: {severity})")
            return True
        except Exception as e:
            log_exception(logger, e, f"add_blacklisted_word({word})")
            return False
    
    def remove_blacklisted_word(self, word_id: int) -> bool:
        """حذف کلمه ممنوعه"""
        try:
            query = "DELETE FROM blacklisted_words WHERE id = %s"
            self.execute_query(query, (word_id,))
            logger.info(f"✅ Blacklisted word removed: ID={word_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"remove_blacklisted_word({word_id})")
            return False
    
    def get_setting(self, key: str, default: str = None) -> str:
        """دریافت تنظیمات"""
        try:
            query = "SELECT value FROM bot_settings WHERE key = %s"
            result = self.execute_query(query, (key,), fetch_one=True)
            return result['value'] if result else default
        except Exception as e:
            log_exception(logger, e, f"get_setting({key})")
            return default
    
    def set_setting(self, key: str, value: str, description: str = None,
                   category: str = "general", updated_by: int = None) -> bool:
        """تنظیم/به‌روزرسانی تنظیمات"""
        try:
            query = """
                INSERT INTO bot_settings 
                (key, value, description, category, updated_at, updated_by)
                VALUES (%s, %s, %s, %s, NOW(), %s)
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    description = EXCLUDED.description,
                    category = EXCLUDED.category,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
            """
            self.execute_query(query, (key, value, description, category, updated_by))
            logger.info(f"✅ Setting {key} updated to: {value}")
            return True
        except Exception as e:
            log_exception(logger, e, f"set_setting({key})")
            return False
    
    def get_all_settings(self, category: str = None) -> List[Dict]:
        """دریافت همه تنظیمات"""
        try:
            if category:
                query = """
                    SELECT * FROM bot_settings WHERE category = %s ORDER BY key
                """
                results = self.execute_query(query, (category,), fetch_all=True)
            else:
                query = "SELECT * FROM bot_settings ORDER BY category, key"
                results = self.execute_query(query, fetch_all=True)
            
            return results
        except Exception as e:
            log_exception(logger, e, "get_all_settings")
            return []
    
    def get_user_notification_preferences(self, user_id: int) -> Optional[dict]:
        """دریافت تنظیمات نوتیفیکیشن کاربر"""
        try:
            query = """
                SELECT enabled, modes, events 
                FROM user_notification_preferences 
                WHERE user_id = %s
            """
            result = self.execute_query(query, (user_id,), fetch_one=True)
            
            if result:
                # ✅ PostgreSQL JSONB به صورت خودکار به dict تبدیل می‌شود
                # اگر TEXT است، json.loads می‌خواهد
                modes = result['modes']
                events = result['events']
                
                # Type safety: اگر string بود، parse کن (backward compatibility)
                if isinstance(modes, str):
                    import json
                    modes = json.loads(modes)
                if isinstance(events, str):
                    import json
                    events = json.loads(events)
                    
                return {
                    'enabled': bool(result['enabled']),
                    'modes': modes,
                    'events': events
                }
            return None
            
        except Exception as e:
            log_exception(logger, e, f"get_user_notification_preferences({user_id})")
            return None
    
    def update_user_notification_preferences(self, user_id: int, preferences: dict) -> bool:
        """به‌روزرسانی تنظیمات نوتیفیکیشن کاربر"""
        try:
            import json
            query = """
                INSERT INTO user_notification_preferences (user_id, enabled, modes, events, updated_at)
                VALUES (%s, %s, %s::jsonb, %s::jsonb, NOW())
                ON CONFLICT(user_id) DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    modes = EXCLUDED.modes,
                    events = EXCLUDED.events,
                    updated_at = NOW()
            """
            # ✅ استفاده از json.dumps برای تبدیل dict به JSON string، سپس cast به JSONB
            self.execute_query(query, (
                user_id,
                preferences.get('enabled', True),
                json.dumps(preferences.get('modes', ['br', 'mp'])),
                json.dumps(preferences.get('events', {}))
            ))
            logger.info(f"✅ Notification preferences updated: user={user_id}")
            return True
            
        except Exception as e:
            log_exception(logger, e, f"update_user_notification_preferences({user_id})")
            return False
    
    def set_user_subscription(self, user_id: int, is_subscriber: bool) -> bool:
        """تنظیم وضعیت اشتراک کاربر"""
        try:
            query = """
                UPDATE users 
                SET is_subscriber = %s 
                WHERE user_id = %s
            """
            self.execute_query(query, (is_subscriber, user_id))
            logger.info(f"✅ User subscription updated: {user_id} -> {is_subscriber}")
            return True
        except Exception as e:
            log_exception(logger, e, f"set_user_subscription({user_id})")
            return False
    
    def get_user_submission_stats(self, user_id: int) -> Optional[Dict]:
        """دریافت آمار ارسال کاربر"""
        try:
            query = """
                SELECT * FROM user_submission_stats WHERE user_id = %s
            """
            row = self.execute_query(query, (user_id,), fetch_one=True)
            # Defaults to ensure stable shape (avoid KeyError in handlers)
            defaults = {
                'user_id': user_id,
                'total_submissions': 0,
                'violation_count': 0,
                'strike_count': 0.0,
                'is_banned': False,
                'daily_submissions': 0,
                'daily_reset_date': None,
                'banned_reason': None,
                'banned_at': None,
                'approved_count': 0,
                'rejected_count': 0,
                'pending_count': 0,
                'last_submission_at': None,
            }

            if row:
                data = dict(row)
                # Merge row over defaults; keep defaults for any missing columns
                merged = {**defaults, **data}
                return merged

            # اگر رکورد نبود، ایجاد کن
            try:
                with self.transaction() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO user_submission_stats (user_id)
                        VALUES (%s)
                    """, (user_id,))
                    cursor.close()
            except Exception as insert_error:
                logger.warning(f"Could not create stats for user {user_id}: {insert_error}")
            
            # Return defaults if no row existed
            return defaults
        except Exception as e:
            log_exception(logger, e, f"get_user_submission_stats({user_id})")
            return None
    
    def update_submission_stats(self, user_id: int, increment_total: bool = False,
                               increment_daily: bool = False, add_violation: int = 0,
                               add_strike: float = 0.0) -> bool:
        """به‌روزرسانی آمار ارسال کاربر"""
        try:
            # بررسی reset روزانه
            from datetime import date
            today = date.today()
            
            stats = self.get_user_submission_stats(user_id)
            if stats and stats.get('daily_reset_date') and str(stats['daily_reset_date']) < str(today):
                # Reset daily count
                with self.transaction() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        UPDATE user_submission_stats
                        SET daily_submissions = 0,
                            daily_reset_date = CURRENT_DATE
                        WHERE user_id = %s
                    """, (user_id,))
                    cursor.close()
            
            with self.transaction() as conn:
                cursor = conn.cursor()
                updates = []
                params = []
                
                if increment_total:
                    updates.append("total_submissions = total_submissions + 1")
                if increment_daily:
                    updates.append("daily_submissions = daily_submissions + 1")
                if add_violation > 0:
                    updates.append("violation_count = violation_count + %s")
                    params.append(add_violation)
                if add_strike > 0:
                    updates.append("strike_count = strike_count + %s")
                    params.append(add_strike)
                
                updates.append("last_submission_at = NOW()")
                params.append(user_id)
                
                query = f"""
                    UPDATE user_submission_stats
                    SET {', '.join(updates)}
                    WHERE user_id = %s
                """
                
                cursor.execute(query, tuple(params))
                cursor.close()
            
            return True
        except Exception as e:
            log_exception(logger, e, f"update_submission_stats({user_id})")
            return False
    
    def submit_attachment_feedback(self, user_id: int, attachment_id: int, 
                                   feedback_text: str) -> bool:
        """ثبت بازخورد متنی برای اتچمنت"""
        try:
            # محدودیت طول
            feedback_text = feedback_text[:500].strip()
            
            if not feedback_text:
                logger.warning(f"Empty feedback rejected: user={user_id}, att={attachment_id}")
                return False
            
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # بررسی وجود رکورد
                cursor.execute("""
                    SELECT id FROM user_attachment_engagement
                    WHERE user_id = %s AND attachment_id = %s
                """, (user_id, attachment_id))
                existing = cursor.fetchone()
                
                if existing:
                    # به‌روزرسانی
                    cursor.execute("""
                        UPDATE user_attachment_engagement
                        SET feedback = %s, last_view_date = NOW()
                        WHERE user_id = %s AND attachment_id = %s
                    """, (feedback_text, user_id, attachment_id))
                else:
                    # ایجاد رکورد جدید
                    cursor.execute("""
                        INSERT INTO user_attachment_engagement
                        (user_id, attachment_id, feedback, first_view_date, last_view_date)
                        VALUES (%s, %s, %s, NOW(), NOW())
                    """, (user_id, attachment_id, feedback_text))
                
                cursor.close()
                logger.info(f"✅ Feedback submitted: user={user_id}, att={attachment_id}")
                return True
                
        except Exception as e:
            log_exception(logger, e, f"submit_attachment_feedback({user_id}, {attachment_id})")
            return False
    
    # ==========================================================================
    # Phase 4: Tickets System - Day 1
    # ==========================================================================
    
    def add_ticket(self, user_id: int, category: str, subject: str,
                   description: str, priority: str = "medium",
                   attachments: List[str] = None) -> Optional[int]:
        """ایجاد تیکت جدید"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO tickets (user_id, category, subject, description, priority)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                """, (user_id, category, subject, description, priority))
                
                result = cursor.fetchone()
                ticket_id = result['id']
                
                # اضافه کردن attachments
                if attachments:
                    for file_id in attachments:
                        cursor.execute("""
                            INSERT INTO ticket_attachments (ticket_id, file_id, file_type)
                            VALUES (%s, %s, 'photo')
                        """, (ticket_id, file_id))
                
                cursor.close()
                logger.info(f"✅ Ticket created: {ticket_id}")
                return ticket_id
        except Exception as e:
            log_exception(logger, e, "add_ticket")
            return None
    
    def get_ticket(self, ticket_id: int) -> Optional[Dict]:
        """دریافت اطلاعات یک تیکت"""
        try:
            query_ticket = "SELECT * FROM tickets WHERE id = %s"
            result = self.execute_query(query_ticket, (ticket_id,), fetch_one=True)
            
            if not result:
                logger.warning(f"Ticket {ticket_id} not found")
                return None
            
            ticket = dict(result)
            
            # دریافت attachments
            query_att = """
                SELECT file_id FROM ticket_attachments 
                WHERE ticket_id = %s AND reply_id IS NULL
            """
            attachments = self.execute_query(query_att, (ticket_id,), fetch_all=True)
            ticket['attachments'] = [row['file_id'] for row in attachments] if attachments else []
            
            return ticket
        except Exception as e:
            log_exception(logger, e, f"get_ticket({ticket_id})")
            return None
    
    def get_user_tickets(self, user_id: int, status: Optional[str] = None) -> List[Dict]:
        """دریافت تیکت‌های کاربر"""
        try:
            if status:
                query = """
                    SELECT * FROM tickets 
                    WHERE user_id = %s AND status = %s 
                    ORDER BY created_at DESC
                """
                results = self.execute_query(query, (user_id, status), fetch_all=True)
            else:
                query = """
                    SELECT * FROM tickets 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC
                """
                results = self.execute_query(query, (user_id,), fetch_all=True)
            
            tickets = [dict(row) for row in results]
            
            # اضافه کردن attachments به هر تیکت
            for ticket in tickets:
                query_att = """
                    SELECT file_id FROM ticket_attachments 
                    WHERE ticket_id = %s AND reply_id IS NULL
                """
                attachments = self.execute_query(query_att, (ticket['id'],), fetch_all=True)
                ticket['attachments'] = [row['file_id'] for row in attachments] if attachments else []
            
            return tickets
        except Exception as e:
            log_exception(logger, e, f"get_user_tickets({user_id})")
            return []
    
    def get_all_tickets(self, status: Optional[str] = None, 
                       assigned_to: Optional[int] = None) -> List[Dict]:
        """دریافت همه تیکت‌ها (برای ادمین)"""
        try:
            query = "SELECT * FROM tickets WHERE TRUE"
            params = []
            
            if status:
                query += " AND status = %s"
                params.append(status)
            
            if assigned_to:
                query += " AND assigned_to = %s"
                params.append(assigned_to)
            
            query += " ORDER BY created_at DESC"
            
            results = self.execute_query(query, tuple(params), fetch_all=True)
            tickets = [dict(row) for row in results]
            
            # اضافه کردن attachments
            for ticket in tickets:
                query_att = """
                    SELECT file_id FROM ticket_attachments 
                    WHERE ticket_id = %s AND reply_id IS NULL
                """
                attachments = self.execute_query(query_att, (ticket['id'],), fetch_all=True)
                ticket['attachments'] = [row['file_id'] for row in attachments] if attachments else []
            
            return tickets
        except Exception as e:
            log_exception(logger, e, "get_all_tickets")
            return []
    
    def add_ticket_reply(self, ticket_id: int, user_id: int, message: str,
                        is_admin: bool = False, attachments: List[str] = None) -> bool:
        """افزودن پاسخ به تیکت"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                cursor.execute("""
                    INSERT INTO ticket_replies (ticket_id, user_id, message, is_admin)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                """, (ticket_id, user_id, message, is_admin))
                
                result = cursor.fetchone()
                reply_id = result['id']
                
                # attachments
                if attachments:
                    for file_id in attachments:
                        cursor.execute("""
                            INSERT INTO ticket_attachments (reply_id, file_id, file_type)
                            VALUES (%s, %s, 'photo')
                        """, (reply_id, file_id))
                
                # به‌روزرسانی زمان
                cursor.execute("""
                    UPDATE tickets SET updated_at = NOW() WHERE id = %s
                """, (ticket_id,))
                
                cursor.close()
                logger.info(f"✅ Reply added to ticket {ticket_id}")
                return True
        except Exception as e:
            log_exception(logger, e, "add_ticket_reply")
            return False
    
    def get_ticket_replies(self, ticket_id: int) -> List[Dict]:
        """دریافت پاسخ‌های تیکت"""
        try:
            query = """
                SELECT * FROM ticket_replies 
                WHERE ticket_id = %s 
                ORDER BY created_at ASC
            """
            results = self.execute_query(query, (ticket_id,), fetch_all=True)
            replies = [dict(row) for row in results]
            
            # اضافه کردن attachments به هر reply
            for reply in replies:
                query_att = """
                    SELECT file_id FROM ticket_attachments WHERE reply_id = %s
                """
                attachments = self.execute_query(query_att, (reply['id'],), fetch_all=True)
                reply['attachments'] = [row['file_id'] for row in attachments] if attachments else []
            
            return replies
        except Exception as e:
            log_exception(logger, e, f"get_ticket_replies({ticket_id})")
            return []
    
    def update_ticket_status(self, ticket_id: int, new_status: str) -> bool:
        """تغییر وضعیت تیکت"""
        try:
            query = """
                UPDATE tickets 
                SET status = %s, updated_at = NOW() 
                WHERE id = %s
            """
            self.execute_query(query, (new_status, ticket_id))
            logger.info(f"✅ Ticket {ticket_id} status updated to: {new_status}")
            return True
        except Exception as e:
            log_exception(logger, e, f"update_ticket_status({ticket_id}, {new_status})")
            return False
    
    def update_ticket_priority(self, ticket_id: int, new_priority: str) -> bool:
        """تغییر اولویت تیکت"""
        try:
            query = """
                UPDATE tickets 
                SET priority = %s, updated_at = NOW() 
                WHERE id = %s
            """
            self.execute_query(query, (new_priority, ticket_id))
            logger.info(f"✅ Ticket {ticket_id} priority updated to: {new_priority}")
            return True
        except Exception as e:
            log_exception(logger, e, f"update_ticket_priority({ticket_id})")
            return False
    
    def assign_ticket(self, ticket_id: int, admin_id: int) -> bool:
        """اختصاص تیکت به ادمین"""
        try:
            query = """
                UPDATE tickets 
                SET assigned_to = %s, status = 'in_progress', updated_at = NOW() 
                WHERE id = %s
            """
            self.execute_query(query, (admin_id, ticket_id))
            logger.info(f"✅ Ticket {ticket_id} assigned to admin {admin_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"assign_ticket({ticket_id})")
            return False
    
    def close_ticket(self, ticket_id: int, admin_id: int, resolution: str = "") -> bool:
        """بستن تیکت"""
        try:
            query = """
                UPDATE tickets 
                SET status = 'closed', closed_at = NOW(), 
                    resolution = %s, updated_at = NOW() 
                WHERE id = %s
            """
            self.execute_query(query, (resolution, ticket_id))
            logger.info(f"✅ Ticket {ticket_id} closed by admin {admin_id}")
            return True
        except Exception as e:
            log_exception(logger, e, f"close_ticket({ticket_id})")
            return False
    
    def search_tickets(self, query: str) -> List[Dict]:
        """جستجوی تیکت‌ها"""
        try:
            search_term = f"%{query}%"
            query_sql = """
                SELECT * FROM tickets 
                WHERE subject ILIKE %s OR description ILIKE %s OR CAST(id AS TEXT) LIKE %s
                ORDER BY created_at DESC
            """
            results = self.execute_query(query_sql, (search_term, search_term, search_term), fetch_all=True)
            return [dict(row) for row in results]
        except Exception as e:
            log_exception(logger, e, f"search_tickets({query})")
            return []
    
    def get_ticket_stats(self, admin_id: Optional[int] = None) -> Dict:
        """آمار تیکت‌ها"""
        try:
            if admin_id:
                query = """
                    SELECT status, COUNT(*) as count 
                    FROM tickets 
                    WHERE assigned_to = %s
                    GROUP BY status
                """
                results = self.execute_query(query, (admin_id,), fetch_all=True)
            else:
                query = """
                    SELECT status, COUNT(*) as count 
                    FROM tickets 
                    GROUP BY status
                """
                results = self.execute_query(query, fetch_all=True)
            
            stats = {row['status']: row['count'] for row in results}
            stats['total'] = sum(stats.values())
            
            return stats
        except Exception as e:
            log_exception(logger, e, "get_ticket_stats")
            return {}
    
    # ==========================================================================
    # Phase 4: FAQ System - Day 2
    # ==========================================================================
    
    def _ensure_faqs_language_column(self):
        """Ensure 'language' column exists on faqs table (rename 'lang' if exists)."""
        try:
            # Check if 'language' column exists
            check_sql = "SELECT column_name FROM information_schema.columns WHERE table_name='faqs' AND column_name='language'"
            # execute_query might fail if we are in a transaction block? No, it should be fine.
            # But wait, execute_query uses self.conn or pool.
            # We should probably just try to select 1 row and catch error, or check information_schema
            
            with self.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM information_schema.columns WHERE table_name='faqs' AND column_name='language'")
                if cursor.fetchone():
                    return # Exists
                
                cursor.execute("SELECT 1 FROM information_schema.columns WHERE table_name='faqs' AND column_name='lang'")
                if cursor.fetchone():
                    # Rename 'lang' to 'language'
                    cursor.execute("ALTER TABLE faqs RENAME COLUMN lang TO language")
                    logger.info("Renamed 'lang' column to 'language' in faqs table")
                else:
                    # Add 'language' column
                    cursor.execute("ALTER TABLE faqs ADD COLUMN IF NOT EXISTS language VARCHAR(8) NOT NULL DEFAULT 'fa'")
                    logger.info("Added 'language' column to faqs table")
                    
        except Exception as e:
            # Just log, don't crash, let the query fail if it must
            log_exception(logger, e, "ensure_faqs_language_column")
    
    def get_faqs(self, category: Optional[str] = None, lang: Optional[str] = None) -> List[Dict]:
        """دریافت FAQ ها (فیلتر بر اساس زبان در صورت ارائه)"""
        # Retry logic to handle missing column (first run or migration)
        for attempt in range(2):
            try:
                # logger.info(f"DEBUG: get_faqs called with category={category}, lang={lang}")
                if category and lang:
                    query = "SELECT * FROM faqs WHERE category = %s AND language = %s ORDER BY views DESC"
                    results = self.execute_query(query, (category, lang), fetch_all=True)
                elif category:
                    query = "SELECT * FROM faqs WHERE category = %s ORDER BY views DESC"
                    results = self.execute_query(query, (category,), fetch_all=True)
                elif lang:
                    query = "SELECT * FROM faqs WHERE language = %s ORDER BY views DESC"
                    results = self.execute_query(query, (lang,), fetch_all=True)
                else:
                    query = "SELECT * FROM faqs ORDER BY views DESC"
                    results = self.execute_query(query, fetch_all=True)
                
                # logger.info(f"DEBUG: get_faqs returning {len(results)} items")
                return [dict(row) for row in results]
                
            except Exception as e:
                error_str = str(e).lower()
                if attempt == 0 and ("column" in error_str and ("lang" in error_str or "language" in error_str)):
                    logger.warning(f"Schema mismatch in get_faqs, attempting fix... Error: {e}")
                    self._ensure_faqs_language_column()
                    continue # Retry once
                
                log_exception(logger, e, "get_faqs")
                return []
        return []
    
    def search_faqs(self, query: str, lang: Optional[str] = None) -> List[Dict]:
        """جستجو در FAQ ها (با فیلتر زبان اختیاری)"""
        try:
            # self._ensure_faqs_language_column() # rely on get_faqs or manual fix usually, but keeping it generic
            search_term = f"%{query}%"
            if lang:
                query_sql = """
                    SELECT * FROM faqs 
                    WHERE (question ILIKE %s OR answer ILIKE %s) AND language = %s
                    ORDER BY views DESC
                """
                params = (search_term, search_term, lang)
            else:
                query_sql = """
                    SELECT * FROM faqs 
                    WHERE question ILIKE %s OR answer ILIKE %s
                    ORDER BY views DESC
                """
                params = (search_term, search_term)
            results = self.execute_query(query_sql, params, fetch_all=True)
            return [dict(row) for row in results]
        except Exception as e:
            # Try to fix if it's column error
            if "column" in str(e).lower():
                 try:
                     self._ensure_faqs_language_column()
                     return self.search_faqs(query, lang) # Recursive retry once (dangerous if loop, but bounded by stack)
                 except:
                     pass
            log_exception(logger, e, f"search_faqs({query})")
            return []
    
    def add_faq(self, question: str, answer: str, category: str = "general", lang: str = 'fa') -> bool:
        """افزودن FAQ جدید (با زبان)"""
        try:
            self._ensure_faqs_language_column()
            query = """
                INSERT INTO faqs (question, answer, category, language)
                VALUES (%s, %s, %s, %s)
            """
            self.execute_query(query, (question, answer, category, lang))
            logger.info(f"✅ FAQ added: {question[:50]}... [{lang}]")
            return True
        except Exception as e:
            log_exception(logger, e, "add_faq")
            return False
    
    def increment_faq_views(self, faq_id: int) -> bool:
        """افزایش تعداد بازدید FAQ"""
        try:
            query = "UPDATE faqs SET views = views + 1 WHERE id = %s"
            self.execute_query(query, (faq_id,))
            return True
        except Exception as e:
            log_exception(logger, e, f"increment_faq_views({faq_id})")
            return False

    def mark_faq_helpful(self, faq_id: int, helpful: bool = True) -> bool:
        """ثبت رای مفید/نامفید برای FAQ
        - اگر helpful=True: افزایش helpful_count
        - اگر helpful=False: افزایش not_helpful_count (در صورت نبود ستون، ستون را اضافه و سپس به‌روزرسانی)
        """
        try:
            if helpful:
                query = "UPDATE faqs SET helpful_count = helpful_count + 1 WHERE id = %s"
                self.execute_query(query, (faq_id,))
                return True
            else:
                # تلاش برای آپدیت not_helpful_count؛ ممکن است ستون وجود نداشته باشد
                try:
                    query = "UPDATE faqs SET not_helpful_count = not_helpful_count + 1 WHERE id = %s"
                    self.execute_query(query, (faq_id,))
                    return True
                except Exception as inner:
                    # اگر ستون وجود نداشت، تلاش برای ایجاد ستون و تکرار عملیات
                    try:
                        alter_sql = (
                            "ALTER TABLE faqs ADD COLUMN IF NOT EXISTS not_helpful_count INTEGER NOT NULL DEFAULT 0;"
                        )
                        self.execute_query(alter_sql)
                        # دوباره سعی کن مقدار را افزایش دهی
                        query = "UPDATE faqs SET not_helpful_count = not_helpful_count + 1 WHERE id = %s"
                        self.execute_query(query, (faq_id,))
                        return True
                    except Exception as inner2:
                        log_exception(logger, inner2, "mark_faq_not_helpful_migration_failed")
                        return False
        except Exception as e:
            log_exception(logger, e, f"mark_faq_helpful({faq_id}, {helpful})")
            return False
    
    def update_faq(self, faq_id: int, question: str = None, 
                   answer: str = None, category: str = None) -> bool:
        """به‌روزرسانی FAQ"""
        try:
            # ساخت query بر اساس فیلدهایی که باید آپدیت شوند
            updates = []
            params = []
            
            if question is not None:
                updates.append("question = %s")
                params.append(question)
            
            if answer is not None:
                updates.append("answer = %s")
                params.append(answer)
            
            if category is not None:
                updates.append("category = %s")
                params.append(category)
            
            if not updates:
                return False
            
            params.append(faq_id)
            query = f"UPDATE faqs SET {', '.join(updates)} WHERE id = %s"
            
            self.execute_query(query, tuple(params))
            logger.info(f"✅ FAQ {faq_id} updated")
            return True
        except Exception as e:
            log_exception(logger, e, f"update_faq({faq_id})")
            return False
    
    def delete_faq(self, faq_id: int) -> bool:
        """حذف FAQ"""
        try:
            query = "DELETE FROM faqs WHERE id = %s"
            self.execute_query(query, (faq_id,))
            logger.info(f"✅ FAQ {faq_id} deleted")
            return True
        except Exception as e:
            log_exception(logger, e, f"delete_faq({faq_id})")
            return False
    
    def vote_faq(self, user_id: int, faq_id: int, helpful: bool = True) -> Dict:
        """ثبت/تغییر رأی کاربر برای FAQ (یک رأی برای هر کاربر)
        - رأی جدید: اضافه می‌شود و شمارنده‌ها به‌روز می‌شود
        - کلیک مجدد روی همان رأی: رأی حذف می‌شود و شمارنده کاهش می‌یابد
        - تغییر رأی: شمارنده قبلی کم و جدید زیاد می‌شود
        خروجی: {success, action, previous_vote, new_vote, helpful_count, not_helpful_count}
        """
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                # قفل رأی کاربر برای این FAQ
                cursor.execute(
                    """
                    SELECT rating FROM user_faq_votes
                    WHERE user_id = %s AND faq_id = %s
                    FOR UPDATE
                    """,
                    (user_id, faq_id),
                )
                row = cursor.fetchone()
                prev = row.get('rating') if row else None
                new_rating = 1 if helpful else -1
                # تعیین action
                if prev is None:
                    action = 'added'
                    final_rating = new_rating
                elif prev == new_rating:
                    action = 'removed'
                    final_rating = None
                else:
                    action = 'changed'
                    final_rating = new_rating
                # UPSERT رأی
                cursor.execute(
                    """
                    INSERT INTO user_faq_votes (user_id, faq_id, rating, updated_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (user_id, faq_id) DO UPDATE
                    SET rating = EXCLUDED.rating,
                        updated_at = NOW()
                    """,
                    (user_id, faq_id, final_rating),
                )
                # محاسبه دلتای شمارنده‌ها
                dh = 0
                dnh = 0
                if action == 'added':
                    if new_rating == 1:
                        dh = 1
                    else:
                        dnh = 1
                elif action == 'removed':
                    if prev == 1:
                        dh = -1
                    elif prev == -1:
                        dnh = -1
                elif action == 'changed':
                    if prev == 1 and new_rating == -1:
                        dh = -1
                        dnh = 1
                    elif prev == -1 and new_rating == 1:
                        dh = 1
                        dnh = -1
                # اعمال بروزرسانی شمارنده‌ها (با ایجاد ستون در صورت نیاز)
                try:
                    cursor.execute(
                        """
                        UPDATE faqs
                        SET helpful_count = GREATEST(helpful_count + %s, 0),
                            not_helpful_count = GREATEST(not_helpful_count + %s, 0),
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (dh, dnh, faq_id),
                    )
                except Exception:
                    # اگر ستون وجود نداشت، اضافه و دوباره اجرا کن
                    cursor.execute(
                        "ALTER TABLE faqs ADD COLUMN IF NOT EXISTS not_helpful_count INTEGER NOT NULL DEFAULT 0;"
                    )
                    cursor.execute(
                        """
                        UPDATE faqs
                        SET helpful_count = GREATEST(helpful_count + %s, 0),
                            not_helpful_count = GREATEST(not_helpful_count + %s, 0),
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (dh, dnh, faq_id),
                    )
                # خواندن شمارنده‌های نهایی
                cursor.execute(
                    "SELECT helpful_count, COALESCE(not_helpful_count, 0) as not_helpful_count FROM faqs WHERE id = %s",
                    (faq_id,),
                )
                counts = cursor.fetchone()
                h = counts.get('helpful_count', 0) if counts else 0
                nh = counts.get('not_helpful_count', 0) if counts else 0
                cursor.close()
                return {
                    'success': True,
                    'action': action,
                    'previous_vote': prev,
                    'new_vote': final_rating if final_rating is not None else 0,
                    'helpful_count': h,
                    'not_helpful_count': nh,
                }
        except Exception as e:
            log_exception(logger, e, f"vote_faq({user_id}, {faq_id}, {helpful})")
            return {'success': False, 'action': 'error', 'error': str(e)}
    
    # ==========================================================================
    # Phase 4: Suggested Attachments - Day 3
    # ==========================================================================
    
    def add_suggested_attachment(self, attachment_id: int, mode: str, priority: int = 999, 
                                reason: str = None, added_by: int = None) -> bool:
        """اضافه کردن اتچمنت به لیست پیشنهادی"""
        try:
            query = """
                INSERT INTO suggested_attachments 
                (attachment_id, mode, priority, reason, added_by)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (attachment_id, mode) DO UPDATE SET
                    priority = EXCLUDED.priority,
                    reason = EXCLUDED.reason,
                    added_by = EXCLUDED.added_by
            """
            self.execute_query(query, (attachment_id, mode, priority, reason, added_by))
            logger.info(f"✅ Attachment {attachment_id} added to suggested list ({mode})")
            return True
        except Exception as e:
            log_exception(logger, e, f"add_suggested_attachment({attachment_id}, {mode})")
            return False
    
    def remove_suggested_attachment(self, attachment_id: int, mode: str) -> bool:
        """حذف اتچمنت از لیست پیشنهادی"""
        try:
            query = """
                DELETE FROM suggested_attachments 
                WHERE attachment_id = %s AND mode = %s
            """
            self.execute_query(query, (attachment_id, mode))
            logger.info(f"✅ Attachment {attachment_id} removed from suggested list ({mode})")
            return True
        except Exception as e:
            log_exception(logger, e, f"remove_suggested_attachment({attachment_id}, {mode})")
            return False
    
    def get_suggested_attachments(self, mode: str) -> List[Dict]:
        """دریافت لیست اتچمنت‌های پیشنهادی"""
        try:
            query = """
                SELECT c.name as category, w.name as weapon, a.mode,
                       a.id, a.code, a.name as att_name, a.image_file_id as image,
                       sa.priority, sa.reason, sa.added_at
                FROM suggested_attachments sa
                JOIN attachments a ON sa.attachment_id = a.id
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories c ON w.category_id = c.id
                WHERE sa.mode = %s
                ORDER BY sa.priority, c.id, w.name
            """
            result = self.execute_query(query, (mode,), fetch_all=True)
            
            items = []
            for row in result:
                items.append({
                    'category': row['category'],
                    'weapon': row['weapon'],
                    'mode': row['mode'],
                    'attachment': {
                        'id': row['id'],
                        'code': row['code'],
                        'name': row['att_name'],
                        'image': row['image'],
                        'priority': row['priority'],
                        'reason': row['reason']
                    }
                })
            
            return items
        except Exception as e:
            log_exception(logger, e, f"get_suggested_attachments({mode})")
            return []
    
    def is_attachment_suggested(self, attachment_id: int, mode: str) -> bool:
        """بررسی اینکه آیا اتچمنت در لیست پیشنهادی هست یا نه"""
        try:
            query = """
                SELECT COUNT(*) as count
                FROM suggested_attachments
                WHERE attachment_id = %s AND mode = %s
            """
            result = self.execute_query(query, (attachment_id, mode), fetch_one=True)
            return result['count'] > 0
        except Exception as e:
            log_exception(logger, e, f"is_attachment_suggested({attachment_id})")
            return False
    
    def clear_suggested_attachments(self, mode: str = None) -> bool:
        """پاک کردن همه اتچمنت‌های پیشنهادی"""
        try:
            if mode:
                query = "DELETE FROM suggested_attachments WHERE mode = %s"
                self.execute_query(query, (mode,))
                logger.info(f"✅ Cleared all suggested attachments for mode {mode}")
            else:
                query = "DELETE FROM suggested_attachments"
                self.execute_query(query)
                logger.info("✅ Cleared all suggested attachments")
            return True
        except Exception as e:
            log_exception(logger, e, "clear_suggested_attachments")
            return False
    
    def get_suggested_count(self, mode: str = None) -> int:
        """دریافت تعداد اتچمنت‌های پیشنهادی"""
        try:
            if mode:
                query = """
                    SELECT COUNT(*) as count
                    FROM suggested_attachments
                    WHERE mode = %s
                """
                result = self.execute_query(query, (mode,), fetch_one=True)
            else:
                query = """
                    SELECT COUNT(*) as count
                    FROM suggested_attachments
                """
                result = self.execute_query(query, fetch_one=True)
            
            return result['count']
        except Exception as e:
            log_exception(logger, e, "get_suggested_count")
            return 0
    
    def get_suggested_ranked(self, mode: str, category: str = None, weapon: str = None) -> List[Dict]:
        """دریافت اتچمنت‌های پیشنهادی با رتبه‌بندی هوشمند (dict-only)"""
        try:
            # ساخت شرط‌های WHERE
            where_clauses = ["sa.mode = %s"]
            params = [mode]
            
            if category:
                where_clauses.append("wc.name = %s")
                params.append(category)
            
            if weapon:
                where_clauses.append("w.name = %s")
                params.append(weapon)
            
            where_sql = " AND ".join(where_clauses)
            
            # کوئری با محاسبه PopScore
            query = f"""
                SELECT 
                    wc.name as category,
                    w.name as weapon,
                    sa.mode,
                    a.id,
                    a.name,
                    a.code,
                    a.image_file_id as image,
                    sa.priority,
                    sa.reason,
                    COALESCE(SUM(CASE WHEN uae.rating = 1 THEN 1 ELSE 0 END), 0) as likes,
                    COALESCE(SUM(CASE WHEN uae.rating = -1 THEN 1 ELSE 0 END), 0) as dislikes,
                    COALESCE(SUM(uae.total_views), 0) as views,
                    -- محاسبه PopScore
                    (1000 - sa.priority) + 
                    (COALESCE(SUM(CASE WHEN uae.rating = 1 THEN 1 ELSE 0 END), 0) * 10) - 
                    (COALESCE(SUM(CASE WHEN uae.rating = -1 THEN 1 ELSE 0 END), 0) * 5) +
                    (COALESCE(SUM(uae.total_views), 0) / 10.0) as pop_score
                FROM suggested_attachments sa
                JOIN attachments a ON sa.attachment_id = a.id
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories wc ON w.category_id = wc.id
                LEFT JOIN user_attachment_engagement uae ON a.id = uae.attachment_id
                WHERE {where_sql}
                GROUP BY a.id, wc.name, w.name, sa.mode, sa.priority, sa.reason
                ORDER BY pop_score DESC, sa.priority ASC, likes DESC
            """
            
            results = self.execute_query(query, tuple(params), fetch_all=True)
            
            # تبدیل به فرمت dict-only
            ranked_list = []
            for row in results:
                att_dict = {
                    'id': row['id'],
                    'name': row['name'],
                    'code': row['code'],
                    'image': row['image'],
                    'priority': row['priority'],
                    'reason': row['reason'],
                    'likes': row['likes'],
                    'dislikes': row['dislikes'],
                    'views': row['views'],
                    'pop_score': round(float(row['pop_score']), 2)
                }
                ranked_list.append({
                    'category': row['category'],
                    'weapon': row['weapon'],
                    'mode': row['mode'],
                    'attachment': att_dict
                })
            
            logger.info(f"Ranked suggestions: mode={mode}, count={len(ranked_list)}")
            return ranked_list
            
        except Exception as e:
            log_exception(logger, e, f"get_suggested_ranked({mode})")
            return []
    
    # ==========================================================================
    # Phase 4: Final Methods (Feedback, Settings, Utility) - Day 4
    # ==========================================================================
    
    def add_feedback(self, user_id: int, rating: int, category: str = "general", message: str = "") -> bool:
        """ثبت بازخورد کاربر"""
        try:
            query = """
                INSERT INTO feedback (user_id, rating, category, message)
                VALUES (%s, %s, %s, %s)
            """
            self.execute_query(query, (user_id, rating, category, message))
            logger.info(f"✅ Feedback added: user={user_id}, rating={rating}")
            return True
        except Exception as e:
            log_exception(logger, e, "add_feedback")
            return False
    
    def get_feedback_stats(self) -> Dict:
        """آمار بازخوردها - بهینه شده"""
        try:
            # یک query برای توزیع + aggregate
            query = """
                SELECT 
                    rating,
                    COUNT(*) as count,
                    (SELECT COUNT(*) FROM feedback) as total,
                    (SELECT AVG(rating) FROM feedback) as avg_rating
                FROM feedback
                GROUP BY rating
            """
            results = self.execute_query(query, fetch_all=True)
            
            if results:
                total = results[0]['total']
                avg_rating = results[0]['avg_rating'] or 0
                distribution = {str(row['rating']): row['count'] for row in results}
            else:
                total = 0
                avg_rating = 0
                distribution = {}
            
            return {
                "average_rating": round(float(avg_rating), 2),
                "total": total,
                "rating_distribution": distribution
            }
        except Exception as e:
            log_exception(logger, e, "get_feedback_stats")
            return {"average_rating": 0, "total": 0, "rating_distribution": {}}
    
    def delete_setting(self, key: str) -> bool:
        """حذف تنظیمات"""
        try:
            query = "DELETE FROM bot_settings WHERE key = %s"
            self.execute_query(query, (key,))
            logger.info(f"✅ Setting {key} deleted")
            return True
        except Exception as e:
            log_exception(logger, e, f"delete_setting({key})")
            return False
    
    def get_ua_setting(self, key: str) -> Optional[str]:
        """دریافت یک تنظیم user_attachment"""
        try:
            query = """
                SELECT setting_value FROM user_attachment_settings 
                WHERE setting_key = %s
            """
            row = self.execute_query(query, (key,), fetch_one=True)
            if row:
                return row['setting_value']
            # Fallback defaults when the setting does not exist yet
            # Enabled by default to expose the feature unless explicitly disabled by admin
            if key == 'system_enabled':
                return '1'
            return None
        except Exception as e:
            log_exception(logger, e, f"get_ua_setting({key})")
            return None
    
    def get_all_ua_settings(self) -> List[Dict]:
        """دریافت تمام تنظیمات user_attachment"""
        try:
            query = """
                SELECT setting_key, setting_value, updated_at, updated_by
                FROM user_attachment_settings
                ORDER BY setting_key
            """
            rows = self.execute_query(query, fetch_all=True)
            return [dict(row) for row in rows]
        except Exception as e:
            log_exception(logger, e, "get_all_ua_settings")
            return []
    
    def get_all_user_attachment_settings(self) -> List[Dict]:
        """Alias for get_all_ua_settings() - used by settings_handler"""
        return self.get_all_ua_settings()
    
    def update_ua_setting(self, key: str, value: str, admin_id: int = None) -> bool:
        """به‌روزرسانی تنظیم user_attachment (UPSERT)"""
        try:
            # Use INSERT ... ON CONFLICT to create or update in one step
            query = """
                INSERT INTO user_attachment_settings (setting_key, setting_value, updated_at, updated_by)
                VALUES (%s, %s, NOW(), %s)
                ON CONFLICT (setting_key) DO UPDATE SET
                    setting_value = EXCLUDED.setting_value,
                    updated_at = NOW(),
                    updated_by = EXCLUDED.updated_by
            """
            self.execute_query(query, (key, value, admin_id))
            logger.info(f"✅ UA Setting upserted: {key} = {value}")
            return True
        except Exception as e:
            log_exception(logger, e, f"update_ua_setting({key})")
            return False
    
    def set_user_attachment_setting(self, key: str, value: str, admin_id: int = None) -> bool:
        """Alias for update_ua_setting() - used by settings_handler"""
        return self.update_ua_setting(key, value, admin_id)
    
    def backup_database(self, backup_dir: str = 'backups') -> str:
        """ایجاد backup از دیتابیس PostgreSQL"""
        import subprocess
        from datetime import datetime
        import os
        
        try:
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(backup_dir, f'postgres_backup_{timestamp}.sql')
            
            # استفاده از pg_dump
            # نیاز به تنظیم متغیرهای محیطی PGPASSWORD یا استفاده از .pgpass
            cmd = [
                'pg_dump',
                '-h', os.getenv('POSTGRES_HOST', 'localhost'),
                '-p', os.getenv('POSTGRES_PORT', '5432'),
                '-U', os.getenv('POSTGRES_USER', 'postgres'),
                '-d', os.getenv('POSTGRES_DB', 'codm_bot'),
                '-F', 'c',  # Custom format
                '-f', backup_file
            ]
            
            # تنظیم password از environment
            env = os.environ.copy()
            if os.getenv('POSTGRES_PASSWORD'):
                env['PGPASSWORD'] = os.getenv('POSTGRES_PASSWORD')
            
            result = subprocess.run(cmd, env=env, capture_output=True, text=True)
            
            if result.returncode == 0:
                logger.info(f"✅ PostgreSQL backup created: {backup_file}")
                return backup_file
            else:
                logger.error(f"pg_dump failed: {result.stderr}")
                return None
                
        except Exception as e:
            log_exception(logger, e, "backup_database")
            return None
    
    def export_data(self, file_path: str) -> bool:
        """Export دیتا به فایل (پیاده‌سازی ساده)"""
        try:
            logger.warning("export_data: Not fully implemented for PostgreSQL")
            # این متد باید در BackupManager پیاده‌سازی شود
            return False
        except Exception as e:
            log_exception(logger, e, "export_data")
            return False
    
    def import_data(self, file_path: str) -> bool:
        """Import دیتا از فایل (پیاده‌سازی ساده)"""
        try:
            logger.warning("import_data: Not fully implemented for PostgreSQL")
            # این متد باید در BackupManager پیاده‌سازی شود
            return False
        except Exception as e:
            log_exception(logger, e, "import_data")
            return False
    
    def close(self):
        """بستن اتصال‌ها (delegate به parent)"""
        try:
            return super().close()
        except Exception as e:
            log_exception(logger, e, "close")

    # ==========================================================================
    # RBAC & Admin Methods
    # ==========================================================================

    def create_role_if_not_exists(self, role_name: str, display_name: str, 
                                 description: str = None, icon: str = None, 
                                 permissions: List[str] = None) -> bool:
        """ایجاد نقش جدید اگر وجود نداشته باشد"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # 1. Create Role
                cursor.execute(
                    """
                    INSERT INTO roles (name, display_name, description, icon)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                        display_name = EXCLUDED.display_name,
                        description = EXCLUDED.description,
                        icon = EXCLUDED.icon
                    RETURNING id
                    """,
                    (role_name, display_name, description, icon)
                )
                role_id = cursor.fetchone()['id']
                
                # 2. Add Permissions
                if permissions:
                    # First clear existing permissions for this role (to sync with code)
                    cursor.execute("DELETE FROM role_permissions WHERE role_id = %s", (role_id,))
                    
                    # Add new permissions
                    if permissions:
                        values = [(role_id, p) for p in permissions]
                        cursor.executemany(
                            "INSERT INTO role_permissions (role_id, permission) VALUES (%s, %s)",
                            values
                        )
                
                return True
        except Exception as e:
            log_exception(logger, e, f"create_role_if_not_exists({role_name})")
            return False

    def get_role(self, role_name: str) -> Optional[Dict]:
        """دریافت اطلاعات کامل یک نقش شامل دسترسی‌ها"""
        try:
            # Get role details
            query = "SELECT * FROM roles WHERE name = %s"
            role = self.execute_query(query, (role_name,), fetch_one=True)
            
            if not role:
                return None
                
            # Get permissions
            query_perms = "SELECT permission FROM role_permissions WHERE role_id = %s"
            perms = self.execute_query(query_perms, (role['id'],), fetch_all=True)
            
            role_dict = dict(role)
            role_dict['permissions'] = [p['permission'] for p in perms]
            return role_dict
        except Exception as e:
            log_exception(logger, e, f"get_role({role_name})")
            return None

    def get_all_roles(self) -> List[Dict]:
        """دریافت تمام نقش‌ها"""
        try:
            query = "SELECT * FROM roles ORDER BY id"
            roles = self.execute_query(query, fetch_all=True)
            
            result = []
            for role in roles:
                # Get permissions for each role
                query_perms = "SELECT permission FROM role_permissions WHERE role_id = %s"
                perms = self.execute_query(query_perms, (role['id'],), fetch_all=True)
                
                role_dict = dict(role)
                role_dict['permissions'] = [p['permission'] for p in perms]
                result.append(role_dict)
                
            return result
        except Exception as e:
            log_exception(logger, e, "get_all_roles")
            return []

    def _ensure_admins_schema(self):
        """Ensure admins table has all required columns"""
        try:
            # First check if is_active column already exists to avoid unnecessary ALTER TABLE
            check_query = """
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'admins' AND column_name = 'is_active'
            """
            result = self.execute_query(check_query, fetch_one=True)
            
            if result:
                # Column already exists, no need to alter
                return
            
            # Column doesn't exist, try to add it
            self.execute_query(
                "ALTER TABLE admins ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;"
            )
        except Exception as e:
            # Ignore error if column already exists (race condition) or other non-critical issues
            # But log it just in case
            logger.warning(f"Schema check for admins table: {e}")

    def is_admin(self, user_id: int) -> bool:
        """بررسی اینکه آیا کاربر ادمین است"""
        try:
            # Ensure schema is correct (temporary fix for migration)
            self._ensure_admins_schema()
            
            query = "SELECT is_active FROM admins WHERE user_id = %s"
            result = self.execute_query(query, (user_id,), fetch_one=True)
            return bool(result and result['is_active'])
        except Exception as e:
            log_exception(logger, e, f"is_admin({user_id})")
            return False

    def get_admin(self, user_id: int) -> Optional[Dict]:
        """دریافت اطلاعات ادمین"""
        try:
            query = """
                SELECT a.*, u.username, u.first_name, u.last_name
                FROM admins a
                JOIN users u ON a.user_id = u.user_id
                WHERE a.user_id = %s
            """
            admin = self.execute_query(query, (user_id,), fetch_one=True)
            
            if not admin:
                return None
                
            # Get roles
            roles = self.get_admin_roles(user_id)
            
            admin_dict = dict(admin)
            # For backward compatibility, set 'role_name' to the first role or 'admin'
            admin_dict['role_name'] = roles[0] if roles else 'admin'
            admin_dict['roles'] = roles
            return admin_dict
        except Exception as e:
            log_exception(logger, e, f"get_admin({user_id})")
            return None

    def get_all_admins(self) -> List[Dict]:
        """دریافت لیست تمام ادمین‌ها"""
        try:
            query = """
                SELECT a.*, u.username, u.first_name, u.last_name
                FROM admins a
                JOIN users u ON a.user_id = u.user_id
                ORDER BY a.created_at DESC
            """
            admins = self.execute_query(query, fetch_all=True)
            
            result = []
            for admin in admins:
                roles = self.get_admin_roles(admin['user_id'])
                admin_dict = dict(admin)
                admin_dict['role_name'] = roles[0] if roles else 'admin'
                admin_dict['roles'] = roles
                result.append(admin_dict)
                
            return result
        except Exception as e:
            log_exception(logger, e, "get_all_admins")
            return []

    def assign_role_to_admin(self, user_id: int, role_name: str, assigned_by: int = None, display_name: str = None) -> bool:
        """اختصاص نقش به ادمین (و ایجاد ادمین اگر نباشد)"""
        try:
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                # 1. Ensure user exists in users table (if not, create dummy)
                cursor.execute("INSERT INTO users (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
                
                # 2. Ensure user exists in admins table with display_name
                if display_name:
                    cursor.execute(
                        """
                        INSERT INTO admins (user_id, is_active, display_name) 
                        VALUES (%s, TRUE, %s)
                        ON CONFLICT (user_id) DO UPDATE SET 
                            is_active = TRUE,
                            display_name = COALESCE(EXCLUDED.display_name, admins.display_name)
                        """, 
                        (user_id, display_name)
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO admins (user_id, is_active) 
                        VALUES (%s, TRUE)
                        ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE
                        """, 
                        (user_id,)
                    )
                
                # 3. Get Role ID
                cursor.execute("SELECT id FROM roles WHERE name = %s", (role_name,))
                role_res = cursor.fetchone()
                if not role_res:
                    logger.error(f"Role not found: {role_name}")
                    return False
                role_id = role_res['id']
                
                # 4. Assign Role
                cursor.execute(
                    """
                    INSERT INTO admin_roles (user_id, role_id, assigned_by)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, role_id) DO NOTHING
                    """,
                    (user_id, role_id, assigned_by)
                )
                
                return True
        except Exception as e:
            log_exception(logger, e, f"assign_role_to_admin({user_id}, {role_name})")
            return False

    def remove_admin(self, user_id: int) -> bool:
        """حذف دسترسی ادمین (غیرفعال کردن)"""
        try:
            # We don't delete from table to keep history, just set inactive
            # But for roles, we might want to clear them? 
            # Let's just set is_active = FALSE and clear roles
            with self.transaction() as conn:
                cursor = conn.cursor()
                
                cursor.execute("UPDATE admins SET is_active = FALSE WHERE user_id = %s", (user_id,))
                cursor.execute("DELETE FROM admin_roles WHERE user_id = %s", (user_id,))
                
                return True
        except Exception as e:
            log_exception(logger, e, f"remove_admin({user_id})")
            return False

    def get_admin_roles(self, user_id: int) -> List[str]:
        """دریافت نام نقش‌های یک ادمین"""
        try:
            query = """
                SELECT r.name
                FROM roles r
                JOIN admin_roles ar ON r.id = ar.role_id
                WHERE ar.user_id = %s
            """
            results = self.execute_query(query, (user_id,), fetch_all=True)
            return [row['name'] for row in results]
        except Exception as e:
            log_exception(logger, e, f"get_admin_roles({user_id})")
            return []
    
    # ==========================================================================
    # Proxy Pattern: Delegate unknown methods to DatabaseSQL
    # ==========================================================================
    
    def __getattr__(self, name):
        """
        Proxy pattern: Delegate به parent class یا raise AttributeError
        
        ✅ Migration Complete: SQLite fallback غیرفعال شده است
        همه 112 متد DatabaseSQL در PostgreSQL پیاده‌سازی شده‌اند
        """
        # جلوگیری از infinite recursion
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")
        
        # سعی کن از parent class بگیری (DatabasePostgres)
        try:
            return super().__getattribute__(name)
        except AttributeError:
            pass
        
        # SQLite fallback غیرفعال - تمام متدها باید در PostgreSQL باشند
        raise AttributeError(
            f"'{type(self).__name__}' has no attribute '{name}'. "
            f"All methods should be implemented in PostgreSQL. "
            f"If you see this error, the method '{name}' needs to be added to DatabasePostgresProxy."
        )

    #
    #     User Attachments Implementation
    #
    
    def get_user_submission_stats(self, user_id: int) -> Dict:
        """دریافت آمار ارسال‌های کاربر"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Ensure user exists in stats
                cursor.execute(
                    """
                    INSERT INTO user_submission_stats (user_id, updated_at)
                    VALUES (%s, NOW())
                    ON CONFLICT (user_id) DO NOTHING
                    """,
                    (user_id,)
                )
                
                # Get stats
                cursor.execute(
                    """
                    SELECT * FROM user_submission_stats WHERE user_id = %s
                    """,
                    (user_id,)
                )
                row = cursor.fetchone()
                
                # Get rejected count (as fallback or addition)
                cursor.execute(
                    "SELECT COUNT(*) as cnt FROM user_attachments WHERE user_id = %s AND status = 'rejected'",
                    (user_id,)
                )
                rejected_count = cursor.fetchone()['cnt']
                
            if not row:
                return {
                    'total_submissions': 0,
                    'approved_submissions': 0,
                    'rejected_submissions': 0,
                    'daily_submissions': 0,
                    'strike_count': 0,
                    'violation_count': 0,
                    'is_banned': False,
                    'banned_reason': None,
                    'banned_at': None
                }
            
            stats = dict(row)
            stats['approved_submissions'] = stats.get('approved_count', 0)
            stats['rejected_submissions'] = rejected_count
            
            # Check daily reset
            today = date.today()
            last_reset = stats.get('daily_reset_date')
            if last_reset != today:
                with self.get_connection() as conn:
                    conn.execute(
                        "UPDATE user_submission_stats SET daily_submissions = 0, daily_reset_date = %s WHERE user_id = %s",
                        (today, user_id)
                    )
                stats['daily_submissions'] = 0
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting user submission stats: {e}")
            return {
                'total_submissions': 0,
                'approved_submissions': 0,
                'rejected_submissions': 0,
                'daily_submissions': 0,
                'strike_count': 0,
                'violation_count': 0,
                'is_banned': False,
                'banned_reason': None,
                'banned_at': None
            }

    def get_user_attachment(self, attachment_id: int) -> Optional[Dict]:
        """دریافت یک اتچمنت خاص"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT ua.*, u.username, u.first_name
                    FROM user_attachments ua
                    LEFT JOIN users u ON ua.user_id = u.user_id
                    WHERE ua.id = %s
                    """,
                    (attachment_id,)
                )
                row = cursor.fetchone()
                
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error getting user attachment {attachment_id}: {e}")
            return None



    def upsert_user(self, user_id: int, username: str = None, first_name: str = None, last_name: str = None):
        """به‌روزرسانی یا ایجاد کاربر"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO users (user_id, username, first_name, last_name, last_seen)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        last_name = EXCLUDED.last_name,
                        last_seen = NOW()
                    """,
                    (user_id, username, first_name, last_name)
                )
        except Exception as e:
            logger.error(f"Error upserting user {user_id}: {e}")

    def update_submission_stats(self, user_id: int, add_violation: int = 0, add_strike: float = 0.0, 
                              increment_total: bool = False, increment_daily: bool = False):
        """به‌روزرسانی آمار کاربر"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                today = date.today()
                
                # Check if daily reset needed first
                cursor.execute("SELECT daily_reset_date FROM user_submission_stats WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                reset_needed = False
                if not row or row['daily_reset_date'] != today:
                    reset_needed = True
                
                # Prepare update
                set_clauses = ["updated_at = NOW()"]
                query_params = []
                
                if add_violation > 0:
                    set_clauses.append("violation_count = violation_count + %s")
                    query_params.append(add_violation)
                
                if add_strike > 0:
                    set_clauses.append("strike_count = strike_count + %s")
                    query_params.append(add_strike)
                    
                if increment_total:
                    set_clauses.append("total_submissions = total_submissions + 1")
                    set_clauses.append("last_submission_at = NOW()")
                    
                if increment_daily:
                    if reset_needed:
                        set_clauses.append("daily_submissions = 1")
                    else:
                        set_clauses.append("daily_submissions = daily_submissions + 1")
                    set_clauses.append("daily_reset_date = %s")
                    query_params.append(today)
                elif reset_needed:
                    set_clauses.append("daily_submissions = 0")
                    set_clauses.append("daily_reset_date = %s")
                    query_params.append(today)
                
                query_params.append(user_id)
                
                cursor.execute(
                    f"UPDATE user_submission_stats SET {', '.join(set_clauses)} WHERE user_id = %s",
                    tuple(query_params)
                )

        except Exception as e:
            logger.error(f"Error updating submission stats for {user_id}: {e}")

    def ban_user_from_submissions(self, user_id: int, reason: str):
        """محروم کردن کاربر"""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO user_submission_stats (user_id, is_banned, banned_reason, banned_at)
                    VALUES (%s, true, %s, NOW())
                    ON CONFLICT (user_id) DO UPDATE SET
                        is_banned = true,
                        banned_reason = EXCLUDED.banned_reason,
                        banned_at = NOW()
                    """,
                    (user_id, reason)
                )
        except Exception as e:
            logger.error(f"Error banning user {user_id}: {e}")

    def get_weapon_by_name(self, category: str, weapon_name: str) -> Optional[Dict]:
        """پیدا کردن سلاح با نام"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM weapons WHERE category = %s AND name = %s",
                    (category, weapon_name)
                )
                row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Error getting weapon {weapon_name}: {e}")
            return None

    def add_user_attachment(self, user_id: int, weapon_id: int, mode: str, category: str,
                          custom_weapon_name: str, attachment_name: str, image_file_id: str,
                          description: str = None) -> Optional[int]:
        """ثبت اتچمنت جدید"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO user_attachments 
                    (user_id, weapon_id, mode, category, custom_weapon_name, attachment_name, 
                     image_file_id, description, status, submitted_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', NOW())
                    RETURNING id
                    """,
                    (user_id, weapon_id, mode, category, custom_weapon_name, attachment_name, 
                     image_file_id, description)
                )
                row = cursor.fetchone()
                if row:
                    return row['id']
            return None
        except Exception as e:
            logger.error(f"Error adding user attachment: {e}")
            return None



    def add_blacklisted_word(self, word: str, category: str, severity: int, added_by: int = None) -> bool:
        """افزودن کلمه ممنوعه"""
        try:
            with self.get_connection() as conn:
                # Check for table columns. Schema: word, category, severity, created_at. NO added_by.
                conn.execute(
                    """
                    INSERT INTO blacklisted_words (word, category, severity, created_at)
                    VALUES (%s, %s, %s, NOW())
                    """,
                    (word, category, severity)
                )
            return True
        except UniqueViolation:
            return False
        except Exception as e:
            logger.error(f"Error adding blacklisted word {word}: {e}")
            return False

    def remove_blacklisted_word(self, word_id: Any) -> bool:
        """حذف کلمه ممنوعه"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Assuming word_id is the word string
                cursor.execute("DELETE FROM blacklisted_words WHERE word = %s", (str(word_id),))
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing blacklisted word {word_id}: {e}")
            return False


# ==============================================================================
# Factory Function
# ==============================================================================

def create_postgres_database(database_url: str = None) -> DatabasePostgresProxy:
    """
    Factory function برای ایجاد PostgreSQL database
    
    Returns:
        DatabasePostgresProxy که تمام متدهای DatabaseSQL را دارد
    """
    return DatabasePostgresProxy(database_url)
