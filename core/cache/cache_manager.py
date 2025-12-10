"""
سیستم Cache Management برای بهبود Performance
این ماژول caching ساده و سریع برای داده‌های استاتیک ارائه می‌دهد
"""

import time
from typing import Any, Optional, Dict, Callable
from functools import wraps
import threading
from utils.logger import get_logger
from utils.metrics import get_metrics, log_cache_access

logger = get_logger('cache', 'cache.log')


class CacheEntry:
    """یک entry در cache با TTL"""
    
    def __init__(self, value: Any, ttl: int):
        self.value = value
        # تبدیل TTL به int اگر string باشد
        ttl_int = int(ttl) if isinstance(ttl, str) else ttl
        self.expiry = time.time() + ttl_int
    
    def is_expired(self) -> bool:
        return time.time() > self.expiry


class CacheManager:
    """
    مدیریت cache با TTL (Time To Live)
    
    این cache برای داده‌هایی مناسبه که:
    - کمتر تغییر می‌کنند (مثل لیست سلاح‌ها، دسته‌بندی‌ها)
    - خواندن‌شون گران است (query به دیتابیس)
    - برای همه کاربران یکسان است
    """
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        # استفاده از metrics centralized به جای internal tracking
        self._metrics = get_metrics()
    
    
    def get(self, key: str) -> Optional[Any]:
        """دریافت مقدار از cache"""
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if not entry.is_expired():
                    log_cache_access(hit=True)
                    logger.debug(f"Cache HIT: {key}")
                    return entry.value
                else:
                    # پاک کردن entry منقضی شده
                    del self._cache[key]
                    self._metrics.cache_metrics.record_eviction()
            
            log_cache_access(hit=False)
            logger.debug(f"Cache MISS: {key}")
            return None
    
    def set(self, key: str, value: Any, ttl: int = 300):
        """ذخیره مقدار در cache با TTL (پیش‌فرض 5 دقیقه)"""
        with self._lock:
            self._cache[key] = CacheEntry(value, ttl)
            logger.debug(f"Cache SET: {key} (TTL={ttl}s)")
    
    def delete(self, key: str):
        """حذف یک key از cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache DELETE: {key}")
    
    def invalidate_pattern(self, pattern: str):
        """حذف همه key هایی که pattern در آنها وجود دارد"""
        with self._lock:
            # تغییر از startswith به in برای پیدا کردن pattern در هر جایی از key
            keys_to_delete = [k for k in self._cache.keys() if pattern in k]
            for key in keys_to_delete:
                del self._cache[key]
            
            if keys_to_delete:
                logger.info(f"Cache INVALIDATE: {len(keys_to_delete)} keys with pattern '{pattern}'")
    
    def clear(self):
        """پاک کردن کل cache"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache CLEAR: {count} entries removed")
    
    def cleanup_expired(self):
        """پاک کردن entry های منقضی شده"""
        with self._lock:
            expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.debug(f"Cache CLEANUP: {len(expired_keys)} expired entries removed")
    
    
    def get_stats(self) -> Dict[str, int]:
        """دریافت آمار cache از metrics مرکزی"""
        cache_stats = self._metrics.cache_metrics.get_stats()
        cache_stats['entries'] = len(self._cache)
        return cache_stats


# Instance سراسری
_cache = CacheManager()


def get_cache() -> CacheManager:
    """دریافت instance سراسری cache"""
    return _cache


def invalidate_attachment_caches(category: str = None, weapon: str = None) -> None:
    """
    پاک کردن تمام cache های مربوط به اتچمنت‌ها
    
    این تابع برای استفاده بعد از افزودن/ویرایش/حذف اتچمنت است.
    
    Args:
        category: نام دسته (اختیاری)
        weapon: نام سلاح (اختیاری)
    """
    patterns = [
        "get_all_attachments",
        "get_weapon_attachments",
        "get_top_attachments",
        "category_counts",
    ]
    
    if category and weapon:
        patterns.append(f"_{category}_{weapon}")
    
    for pattern in patterns:
        _cache.invalidate_pattern(pattern)
    
    # حذف key های خاص
    _cache.delete("category_counts")
    
    logger.info(f"Attachment caches invalidated (category={category}, weapon={weapon})")


def cached(ttl_or_key = 300, key_func: Optional[Callable] = None, ttl: Optional[int] = None):
    """
    Decorator برای cache کردن خروجی توابع
    
    Args:
        ttl_or_key: مدت زمان cache (ثانیه) یا cache key (string)
        key_func: تابع برای ساخت cache key (اختیاری)
        ttl: مدت زمان cache (keyword argument برای backward compatibility)
    
    مثال:
        @cached(ttl=600)
        @cached('my_key')  # با cache key ثابت
        def get_weapons_in_category(category):
            # این تابع فقط هر 10 دقیقه یکبار اجرا می‌شود
            return expensive_db_query(category)
    """
    # تشخیص ttl و cache_key
    if ttl is not None:
        # کاربر از ttl= استفاده کرده
        cache_ttl = ttl
        cache_key_prefix = None
    elif isinstance(ttl_or_key, str):
        # اولین آرگومان یک string است (cache key)
        cache_key_prefix = ttl_or_key
        cache_ttl = 300  # پیش‌فرض 5 دقیقه
    else:
        # اولین آرگومان یک عدد است (ttl)
        cache_key_prefix = None
        cache_ttl = ttl_or_key if isinstance(ttl_or_key, int) else 300
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # ساخت cache key
            if cache_key_prefix:
                # استفاده از cache key ثابت
                cache_key = cache_key_prefix
            elif key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # ساخت key پیش‌فرض از نام تابع و آرگومان‌ها
                func_name = func.__qualname__
                args_str = '_'.join(str(arg) for arg in args)
                kwargs_str = '_'.join(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = f"{func_name}:{args_str}:{kwargs_str}"
            
            # بررسی cache
            cached_value = _cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # اجرای تابع و ذخیره در cache
            result = func(*args, **kwargs)
            _cache.set(cache_key, result, cache_ttl)
            
            return result
        
        # اضافه کردن متد برای پاک کردن cache این تابع
        wrapper.cache_clear = lambda: _cache.invalidate_pattern(func.__qualname__)
        
        return wrapper
    return decorator


def invalidate_cache_on_write(patterns: list):
    """
    Decorator برای invalidate کردن cache بعد از write operations
    
    مثال:
        @invalidate_cache_on_write(['get_weapons_in_category', 'get_all_attachments'])
        def add_weapon(category, name):
            # بعد از اجرا، cache مربوط به این توابع پاک می‌شود
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            
            # اگر عملیات موفق بود، cache را پاک کن
            if result:  # فقط اگر update/add/delete موفق بود
                # Invalidate cache patterns
                for pattern in patterns:
                    _cache.invalidate_pattern(pattern)
                    logger.debug(f"Invalidated cache pattern: {pattern}")
                
                # برای اطمینان بیشتر، همه cache های مربوط به database را پاک کن
                if 'attachments' in str(patterns):  # اگر مربوط به attachments بود
                    _cache.invalidate_pattern('DatabaseAdapter')
                    logger.info("Cleared all DatabaseAdapter cache due to attachment change")
            
            return result
        return wrapper
    return decorator


# Cleanup task برای پاک کردن خودکار expired entries
import asyncio

async def cache_cleanup_task():
    """Task برای پاک کردن خودکار cache های منقضی شده"""
    while True:
        await asyncio.sleep(60)  # هر 1 دقیقه
        _cache.cleanup_expired()
