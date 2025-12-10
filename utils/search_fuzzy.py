"""
موتور جستجوی Fuzzy برای تحمل تایپوها و مطابقت هوشمند
"""

from fuzzywuzzy import fuzz, process
from typing import List, Tuple, Dict, Optional
import threading
import time
from utils.logger import get_logger

logger = get_logger('search.fuzzy', 'user.log')


class FuzzySearchEngine:
    """موتور جستجوی Fuzzy با cache و بهینه‌سازی"""
    
    def __init__(self, db):
        self.db = db
        self._cache = {
            'weapons': [],
            'attachments': [],
            'codes': []
        }
        self._cache_lock = threading.Lock()
        self._cache_time = 0
        self._cache_ttl = 3600  # 1 ساعت
        
        logger.info("FuzzySearchEngine initialized")
    
    def _should_rebuild_cache(self) -> bool:
        """بررسی نیاز به rebuild کردن cache"""
        if not self._cache['weapons']:
            return True
        
        # اگر cache قدیمی شده
        if time.time() - self._cache_time > self._cache_ttl:
            return True
        
        return False
    
    def build_search_index(self, force: bool = False):
        """ساخت index برای جستجوی fuzzy
        
        Args:
            force: اجبار به rebuild حتی اگر cache معتبر باشد
        """
        if not force and not self._should_rebuild_cache():
            logger.debug("Using cached search index")
            return
        
        logger.info("Building fuzzy search index...")
        start_time = time.time()
        
        with self._cache_lock:
            try:
                # استفاده از connection pool به صورت امن
                with self.db.get_connection() as conn:
                    cursor = conn.cursor()
                    
                    # دریافت تمام نام‌های سلاح (unique)
                    cursor.execute("""
                        SELECT DISTINCT name FROM weapons ORDER BY name
                    """)
                    weapons = cursor.fetchall()
                    self._cache['weapons'] = [w['name'] for w in weapons]
                    
                    # دریافت تمام نام‌های اتچمنت (unique)
                    cursor.execute("""
                        SELECT DISTINCT name FROM attachments ORDER BY name
                    """)
                    attachments = cursor.fetchall()
                    self._cache['attachments'] = [a['name'] for a in attachments]
                    
                    # دریافت تمام کدها (unique)
                    cursor.execute("""
                        SELECT DISTINCT code FROM attachments ORDER BY code
                    """)
                    codes = cursor.fetchall()
                    self._cache['codes'] = [c['code'] for c in codes]
                    
                    cursor.close()
                
                self._cache_time = time.time()
                
                elapsed = time.time() - start_time
                logger.info(
                    f"Fuzzy index built in {elapsed:.3f}s: "
                    f"{len(self._cache['weapons'])} weapons, "
                    f"{len(self._cache['attachments'])} attachments, "
                    f"{len(self._cache['codes'])} codes"
                )
                
            except Exception as e:
                logger.error(f"Error building fuzzy index: {e}")
                raise
    
    def fuzzy_match_weapons(self, query: str, threshold: int = 70, limit: int = 5) -> List[Tuple[str, int]]:
        """پیدا کردن سلاح‌های مشابه با query
        
        Args:
            query: متن جستجو
            threshold: حداقل امتیاز مطابقت (0-100)
            limit: حداکثر تعداد نتایج
            
        Returns:
            لیست (نام سلاح, امتیاز)
        """
        if not self._cache['weapons']:
            self.build_search_index()
        
        if not query or len(query) < 2:
            return []
        
        try:
            matches = process.extract(
                query,
                self._cache['weapons'],
                scorer=fuzz.ratio,  # تغییر به ratio برای matching دقیق‌تر
                limit=limit
            )
            
            # فیلتر بر اساس threshold
            results = [(name, score) for name, score in matches if score >= threshold]
            
            logger.debug(f"Fuzzy weapon matches for '{query}': {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in fuzzy weapon matching: {e}")
            return []
    
    def fuzzy_match_attachments(self, query: str, threshold: int = 70, limit: int = 10) -> List[Tuple[str, int]]:
        """پیدا کردن اتچمنت‌های مشابه با query
        
        Args:
            query: متن جستجو
            threshold: حداقل امتیاز مطابقت (0-100)
            limit: حداکثر تعداد نتایج
            
        Returns:
            لیست (نام اتچمنت, امتیاز)
        """
        if not self._cache['attachments']:
            self.build_search_index()
        
        if not query or len(query) < 2:
            return []
        
        try:
            matches = process.extract(
                query,
                self._cache['attachments'],
                scorer=fuzz.ratio,  # تغییر به ratio برای matching دقیق‌تر
                limit=limit
            )
            
            results = [(name, score) for name, score in matches if score >= threshold]
            
            logger.debug(f"Fuzzy attachment matches for '{query}': {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in fuzzy attachment matching: {e}")
            return []
    
    def fuzzy_match_codes(self, query: str, threshold: int = 80, limit: int = 5) -> List[Tuple[str, int]]:
        """پیدا کردن کدهای مشابه با query
        
        Args:
            query: متن جستجو
            threshold: حداقل امتیاز (برای کدها باید بالاتر باشد)
            limit: حداکثر تعداد نتایج
            
        Returns:
            لیست (کد, امتیاز)
        """
        if not self._cache['codes']:
            self.build_search_index()
        
        if not query or len(query) < 2:
            return []
        
        try:
            matches = process.extract(
                query,
                self._cache['codes'],
                scorer=fuzz.ratio,  # برای کدها از ratio استفاده می‌کنیم
                limit=limit
            )
            
            results = [(code, score) for code, score in matches if score >= threshold]
            
            logger.debug(f"Fuzzy code matches for '{query}': {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Error in fuzzy code matching: {e}")
            return []
    
    def fuzzy_match(self, query: str, threshold: int = 70) -> Dict[str, List[Tuple[str, int]]]:
        """جستجوی جامع در همه موارد
        
        Args:
            query: متن جستجو
            threshold: حداقل امتیاز مطابقت
            
        Returns:
            دیکشنری {'weapons': [...], 'attachments': [...], 'codes': [...]}
        """
        return {
            'weapons': self.fuzzy_match_weapons(query, threshold, limit=5),
            'attachments': self.fuzzy_match_attachments(query, threshold, limit=10),
            'codes': self.fuzzy_match_codes(query, max(threshold, 80), limit=5)
        }
    
    def search_with_fuzzy(self, query: str, max_results: int = 30) -> List[Dict]:
        """جستجوی هوشمند با ترکیب FTS5 و Fuzzy (dict-only)
        
        Args:
            query: متن جستجو
            max_results: حداکثر تعداد نتایج
            
        Returns:
            List[Dict]: هر آیتم شامل کلیدهای 'category', 'weapon', 'mode', 'attachment'
        """
        logger.info(f"Fuzzy search started for: '{query}'")
        start_time = time.time()
        
        try:
            # مرحله 1: جستجوی مستقیم با FTS5
            if hasattr(self.db, 'search_attachments_fts'):
                exact_results = self.db.search_attachments_fts(query, limit=max_results)
            else:
                exact_results = self.db.search_attachments(query)
            
            logger.debug(f"FTS5 found {len(exact_results)} exact results")
            
            # اگر نتیجه کافی بود، همین‌ها را برگردان
            if len(exact_results) >= max_results:  # 100% - همیشه fuzzy را هم امتحان کن
                elapsed = time.time() - start_time
                logger.info(f"Fuzzy search completed in {elapsed:.3f}s with {len(exact_results)} results")
                return exact_results[:max_results]
            
            # مرحله 2: اگر نتیجه کم بود، Fuzzy را امتحان کن
            logger.debug("Trying fuzzy matching for more results")
            fuzzy_matches = self.fuzzy_match(query, threshold=75)  # threshold بالاتر برای نتایج دقیق‌تر
            
            # ترکیب نتایج
            combined_results = list(exact_results)
            seen_keys = set()
            
            # اضافه کردن کلید‌های موجود به seen
            for item in exact_results:
                try:
                    att = (item or {}).get('attachment', {})
                    key = (
                        (item or {}).get('category'),
                        (item or {}).get('weapon'),
                        (item or {}).get('mode'),
                        att.get('code')
                    )
                    seen_keys.add(key)
                except Exception:
                    pass
            
            # جستجو بر اساس نام سلاح‌های Fuzzy
            for weapon_name, score in fuzzy_matches['weapons']:
                if len(combined_results) >= max_results:
                    break
                
                try:
                    weapon_results = self.db.search_attachments_fts(weapon_name, limit=10)
                    for item in weapon_results:
                        try:
                            att = (item or {}).get('attachment', {})
                            key = (
                                (item or {}).get('category'),
                                (item or {}).get('weapon'),
                                (item or {}).get('mode'),
                                att.get('code')
                            )
                            if key not in seen_keys:
                                combined_results.append(item)
                                seen_keys.add(key)
                        except Exception:
                            pass
                            
                            if len(combined_results) >= max_results:
                                break
                except Exception as e:
                    logger.warning(f"Error searching weapon '{weapon_name}': {e}")
            
            # جستجو بر اساس نام اتچمنت‌های Fuzzy
            for att_name, score in fuzzy_matches['attachments']:
                if len(combined_results) >= max_results:
                    break
                
                try:
                    att_results = self.db.search_attachments_fts(att_name, limit=5)
                    for item in att_results:
                        try:
                            att = (item or {}).get('attachment', {})
                            key = (
                                (item or {}).get('category'),
                                (item or {}).get('weapon'),
                                (item or {}).get('mode'),
                                att.get('code')
                            )
                            if key not in seen_keys:
                                combined_results.append(item)
                                seen_keys.add(key)
                        except Exception:
                            pass
                            
                            if len(combined_results) >= max_results:
                                break
                except Exception as e:
                    logger.warning(f"Error searching attachment '{att_name}': {e}")
            
            # جستجو بر اساس کدهای Fuzzy
            for code, score in fuzzy_matches['codes']:
                if len(combined_results) >= max_results:
                    break
                
                try:
                    code_results = self.db.search_attachments_fts(code, limit=5)
                    for item in code_results:
                        try:
                            att = (item or {}).get('attachment', {})
                            key = (
                                (item or {}).get('category'),
                                (item or {}).get('weapon'),
                                (item or {}).get('mode'),
                                att.get('code')
                            )
                            if key not in seen_keys:
                                combined_results.append(item)
                                seen_keys.add(key)
                        except Exception:
                            pass
                            
                            if len(combined_results) >= max_results:
                                break
                except Exception as e:
                    logger.warning(f"Error searching code '{code}': {e}")
            
            elapsed = time.time() - start_time
            logger.info(
                f"Fuzzy search completed in {elapsed:.3f}s: "
                f"{len(exact_results)} exact + {len(combined_results) - len(exact_results)} fuzzy = "
                f"{len(combined_results)} total results"
            )
            
            return combined_results[:max_results]
            
        except Exception as e:
            logger.error(f"Error in fuzzy search: {e}")
            # Fallback به جستجوی عادی
            return self.db.search_attachments(query)
    
    def get_suggestions(self, partial_query: str, limit: int = 5) -> List[str]:
        """پیشنهادات سریع بر اساس query جزئی
        
        Args:
            partial_query: query ناقص
            limit: حداکثر پیشنهادات
            
        Returns:
            لیست پیشنهادات
        """
        if not partial_query or len(partial_query) < 2:
            return []
        
        suggestions = []
        
        # مرحله 1: Prefix matching در سلاح‌ها
        for weapon in self._cache['weapons']:
            if weapon.lower().startswith(partial_query.lower()):
                suggestions.append(weapon)
                if len(suggestions) >= limit:
                    return suggestions
        
        # مرحله 2: Fuzzy matching
        if len(suggestions) < limit:
            fuzzy_weapons = self.fuzzy_match_weapons(partial_query, threshold=80, limit=limit - len(suggestions))
            for weapon, score in fuzzy_weapons:
                if weapon not in suggestions:
                    suggestions.append(weapon)
        
        return suggestions[:limit]
    
    def clear_cache(self):
        """پاک کردن cache"""
        with self._cache_lock:
            self._cache = {
                'weapons': [],
                'attachments': [],
                'codes': []
            }
            self._cache_time = 0
            logger.info("Fuzzy search cache cleared")
