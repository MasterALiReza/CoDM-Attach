"""
Smart Cache System with Intelligent TTL Management
بهینه‌سازی cache برای 500-800 کاربر همزمان
"""

from functools import wraps
from typing import Any, Dict, Optional, Callable
import hashlib
import json
import time
import threading
from collections import OrderedDict
from utils.logger import get_logger

logger = get_logger('smart_cache', 'cache.log')


class SmartCacheManager:
    """
    Smart Cache با TTL های هوشمند برای انواع مختلف داده
    
    Features:
    - Dynamic TTL based on data type
    - Cache warming
    - Hit rate tracking
    - Thread-safe operations
    - Memory-efficient (LRU Eviction)
    """
    
    # TTL Configuration (in seconds)
    TTL_CONFIG = {
        # Static data - long TTL
        'categories': 3600,        # 1 hour - دسته‌بندی‌ها کم تغییر می‌کنند
        'weapon_list': 1800,       # 30 min - لیست سلاح‌ها
        'guides': 1800,            # 30 min - راهنماها
        
        # Semi-dynamic data - medium TTL
        'attachments': 300,        # 5 min - اتچمنت‌ها
        'top_attachments': 600,    # 10 min - اتچمنت‌های برتر
        'season_top': 900,         # 15 min - برترین‌های فصل
        
        # Dynamic data - short TTL
        'user_data': 60,           # 1 min - داده‌های کاربر
        'search_results': 120,     # 2 min - نتایج جستجو
        'statistics': 300,         # 5 min - آمار
        
        # Real-time data - very short TTL
        'pending_count': 30,       # 30 sec - تعداد در انتظار
        'online_users': 15,        # 15 sec - کاربران آنلاین
        
        # Default
        'default': 300             # 5 min
    }
    
    MAX_CACHE_SIZE = 10000  # Maximum number of entries
    
    def __init__(self):
        self._cache: OrderedDict[str, Dict] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'evictions': 0,
            'hit_rate': 0.0
        }
        
        # Start cleanup thread
        self._start_cleanup_thread()
    
    def _make_key(self, func_name: str, args: tuple, kwargs: dict, data_type: str = None) -> str:
        """
        Generate unique cache key
        """
        key_data = {
            'func': func_name,
            'args': str(args),
            'kwargs': str(sorted(kwargs.items())),
            'type': data_type
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        """
        with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                
                # Check expiry
                if time.time() < entry['expires_at']:
                    self._stats['hits'] += 1
                    self._update_hit_rate()
                    # Move to end (recently used)
                    self._cache.move_to_end(key)
                    logger.debug(f"Cache HIT: {key[:8]}... (TTL remaining: {entry['expires_at'] - time.time():.1f}s)")
                    return entry['value']
                else:
                    # Expired - remove it
                    del self._cache[key]
                    self._stats['evictions'] += 1
            
            self._stats['misses'] += 1
            self._update_hit_rate()
            logger.debug(f"Cache MISS: {key[:8]}...")
            return None
    
    def set(self, key: str, value: Any, data_type: str = 'default', ttl: Optional[int] = None):
        """
        Set value in cache with smart TTL and LRU eviction
        """
        # Determine TTL
        if ttl is None:
            ttl = self.TTL_CONFIG.get(data_type, self.TTL_CONFIG['default'])
        
        with self._lock:
            # LRU Eviction: If cache is full and key is new, remove oldest
            if key not in self._cache and len(self._cache) >= self.MAX_CACHE_SIZE:
                self._cache.popitem(last=False)  # Remove first (oldest) item
                self._stats['evictions'] += 1
                logger.debug("Cache full, evicted oldest entry")

            self._cache[key] = {
                'value': value,
                'expires_at': time.time() + ttl,
                'data_type': data_type,
                'created_at': time.time()
            }
            # Move to end (recently used)
            self._cache.move_to_end(key)
            self._stats['sets'] += 1
            
        logger.debug(f"Cache SET: {key[:8]}... (type={data_type}, TTL={ttl}s)")
    
    def delete(self, key: str):
        """
        Delete specific key from cache
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache DELETE: {key[:8]}...")
    
    def invalidate_pattern(self, pattern: str):
        """
        Invalidate all keys containing pattern
        """
        with self._lock:
            keys_to_delete = []
            
            # Find matching keys
            for key, entry in self._cache.items():
                if pattern in entry.get('data_type', '') or pattern in key:
                    keys_to_delete.append(key)
            
            # Delete them
            for key in keys_to_delete:
                del self._cache[key]
            
            if keys_to_delete:
                logger.info(f"Cache INVALIDATE: {len(keys_to_delete)} keys with pattern '{pattern}'")
    
    def clear(self):
        """
        Clear entire cache
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache CLEAR: {count} entries removed")
    
    def _cleanup_expired(self):
        """
        Remove expired entries
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, entry in self._cache.items()
                if current_time >= entry['expires_at']
            ]
            
            for key in expired_keys:
                del self._cache[key]
                self._stats['evictions'] += 1
            
            if expired_keys:
                logger.debug(f"Cache CLEANUP: {len(expired_keys)} expired entries removed")
    
    def _start_cleanup_thread(self):
        """
        Start background cleanup thread
        """
        def cleanup_loop():
            while True:
                time.sleep(60)  # Cleanup every minute
                try:
                    self._cleanup_expired()
                except Exception as e:
                    logger.error(f"Cleanup error: {e}")
        
        thread = threading.Thread(target=cleanup_loop, daemon=True)
        thread.start()
    
    def _update_hit_rate(self):
        """
        Update hit rate statistics
        """
        total = self._stats['hits'] + self._stats['misses']
        if total > 0:
            self._stats['hit_rate'] = (self._stats['hits'] / total) * 100
    
    def get_stats(self) -> Dict:
        """
        Get cache statistics
        """
        with self._lock:
            return {
                **self._stats,
                'entries': len(self._cache),
                'memory_mb': self._estimate_memory() / (1024 * 1024)
            }
    
    def _estimate_memory(self) -> int:
        """
        Estimate memory usage (bytes)
        """
        # Rough estimation
        import sys
        total = 0
        for key, entry in self._cache.items():
            total += sys.getsizeof(key)
            total += sys.getsizeof(entry)
        return total
    
    def warm_cache(self, db):
        """
        Pre-populate cache with frequently accessed data
        """
        logger.info("Starting cache warming...")
        
        try:
            # Categories (static data)
            categories = ['assault_rifle', 'smg', 'lmg', 'sniper', 'marksman', 'shotgun', 'pistol', 'launcher']
            
            for category in categories:
                # Cache weapon list
                key = self._make_key('get_weapons_in_category', (category,), {}, 'weapon_list')
                weapons = db.get_weapons_in_category(category)
                self.set(key, weapons, 'weapon_list')
                
                # Cache top attachments for popular weapons (first 3)
                for weapon in weapons[:3]:
                    for mode in ['mp', 'br']:
                        key = self._make_key('get_top_attachments', (category, weapon, mode), {}, 'top_attachments')
                        attachments = db.get_top_attachments(category, weapon, mode)
                        self.set(key, attachments, 'top_attachments')
            
            logger.info(f"Cache warming completed. {len(self._cache)} entries pre-loaded")
            
        except Exception as e:
            logger.error(f"Cache warming error: {e}")


# Decorator for smart caching
def smart_cached(data_type: str = 'default', ttl: Optional[int] = None):
    """
    Smart cache decorator with automatic TTL selection
    
    Usage:
        @smart_cached('weapon_list')
        def get_weapons(category):
            # expensive database query
            return weapons
    """
    def decorator(func):
        # Get or create cache instance
        if not hasattr(smart_cached, '_cache'):
            smart_cached._cache = SmartCacheManager()
        
        cache = smart_cached._cache
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            key = cache._make_key(func.__name__, args, kwargs, data_type)
            
            # Try to get from cache
            cached_value = cache.get(key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = func(*args, **kwargs)
            
            # Store in cache
            cache.set(key, result, data_type, ttl)
            
            return result
        
        # Add invalidate method
        wrapper.invalidate = lambda: cache.invalidate_pattern(func.__name__)
        wrapper.cache = cache
        
        return wrapper
    
    return decorator


def invalidate_on_change(patterns: list):
    """
    Decorator to invalidate cache when data changes
    
    Usage:
        @invalidate_on_change(['weapon', 'attachment'])
        def add_weapon(category, name):
            # add weapon
            return success
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Execute function
            result = func(*args, **kwargs)
            
            # If successful, invalidate cache
            if result:
                cache = getattr(smart_cached, '_cache', None)
                if cache:
                    for pattern in patterns:
                        cache.invalidate_pattern(pattern)
            
            return result
        
        return wrapper
    
    return decorator


# Global cache instance
_smart_cache_instance = None


def get_smart_cache() -> SmartCacheManager:
    """
    Get global smart cache instance (singleton)
    """
    global _smart_cache_instance
    if _smart_cache_instance is None:
        _smart_cache_instance = SmartCacheManager()
    return _smart_cache_instance
