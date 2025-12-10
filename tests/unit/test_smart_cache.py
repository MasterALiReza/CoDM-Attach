import pytest
import time
import threading
from core.cache.smart_cache import SmartCacheManager

class TestSmartCacheManager:
    
    @pytest.fixture
    def cache(self):
        manager = SmartCacheManager()
        # Reset cache for each test
        manager._cache.clear()
        manager._stats = {k: 0 for k in manager._stats}
        return manager

    def test_set_get(self, cache):
        """Test basic set and get operations"""
        cache.set("test_key", "test_value")
        assert cache.get("test_key") == "test_value"
        assert cache._stats['sets'] == 1
        assert cache._stats['hits'] == 1

    def test_ttl_expiry(self, cache):
        """Test that items expire after TTL"""
        # Set with very short TTL
        cache.set("short_lived", "value", ttl=0.1)
        assert cache.get("short_lived") == "value"
        
        time.sleep(0.2)
        assert cache.get("short_lived") is None
        assert cache._stats['evictions'] >= 1

    def test_lru_eviction(self, cache):
        """Test LRU eviction policy"""
        # Temporarily lower max size for testing
        original_max = cache.MAX_CACHE_SIZE
        cache.MAX_CACHE_SIZE = 3
        
        try:
            cache.set("k1", "v1")
            cache.set("k2", "v2")
            cache.set("k3", "v3")
            
            assert len(cache._cache) == 3
            
            # Access k1 to make it recent
            cache.get("k1")
            
            # Add k4, should evict k2 (LRU) - k1 is recent, k3 is recent-ish, k2 is oldest unused?
            # Wait, insertion order: k1, k2, k3. 
            # Access k1 -> k2, k3, k1 (if moved to end)
            # Add k4 -> evict k2?
            cache.set("k4", "v4")
            
            assert len(cache._cache) == 3
            assert cache.get("k2") is None
            assert cache.get("k1") == "v1"
            assert cache.get("k4") == "v4"
        finally:
            cache.MAX_CACHE_SIZE = original_max

    def test_thread_safety(self, cache):
        """Test thread safety with concurrent writes"""
        def worker():
            for i in range(100):
                cache.set(f"thread_{threading.get_ident()}_{i}", i)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
            
        # Just ensure no exceptions occurred and size is reasonable
        assert len(cache._cache) <= cache.MAX_CACHE_SIZE
