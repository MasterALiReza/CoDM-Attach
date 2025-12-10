"""
سیستم Rate Limiting برای جلوگیری از ban شدن ربات
"""

import asyncio
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from collections import deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimit:
    """تعریف محدودیت نرخ"""
    calls: int  # تعداد فراخوانی‌های مجاز
    period: int  # بازه زمانی (ثانیه)
    burst: Optional[int] = None  # حداکثر burst مجاز


class RateLimiter:
    """مدیریت rate limiting برای عملیات‌های مختلف"""
    
    # محدودیت‌های تلگرام
    TELEGRAM_LIMITS = {
        'broadcast': RateLimit(calls=30, period=1),  # 30 پیام در ثانیه
        'bulk_message': RateLimit(calls=30, period=1, burst=50),
        'api_call': RateLimit(calls=30, period=1),
        'file_upload': RateLimit(calls=10, period=1),
    }
    
    def __init__(self):
        self.call_history: Dict[str, deque] = {}
        self.locks: Dict[str, asyncio.Lock] = {}
        
    def _get_history(self, key: str) -> deque:
        """دریافت تاریخچه فراخوانی‌ها"""
        if key not in self.call_history:
            self.call_history[key] = deque(maxlen=1000)
        return self.call_history[key]
    
    def _get_lock(self, key: str) -> asyncio.Lock:
        """دریافت lock برای یک کلید"""
        if key not in self.locks:
            self.locks[key] = asyncio.Lock()
        return self.locks[key]
    
    def _clean_history(self, history: deque, period: int):
        """پاکسازی تاریخچه قدیمی"""
        current_time = time.time()
        cutoff = current_time - period
        
        while history and history[0] < cutoff:
            history.popleft()
    
    async def check_rate_limit(self, key: str, limit: Optional[RateLimit] = None) -> tuple[bool, float]:
        """
        بررسی rate limit
        Returns: (is_allowed, wait_time)
        """
        if limit is None:
            limit = self.TELEGRAM_LIMITS.get(key, RateLimit(calls=30, period=1))
        
        async with self._get_lock(key):
            history = self._get_history(key)
            current_time = time.time()
            
            # پاکسازی تاریخچه قدیمی
            self._clean_history(history, limit.period)
            
            # بررسی تعداد فراخوانی‌ها
            if len(history) >= limit.calls:
                # محاسبه زمان انتظار
                oldest_call = history[0]
                wait_time = limit.period - (current_time - oldest_call)
                if wait_time > 0:
                    return False, wait_time
            
            # ثبت فراخوانی جدید
            history.append(current_time)
            return True, 0
    
    async def wait_if_needed(self, key: str, limit: Optional[RateLimit] = None):
        """صبر کردن در صورت نیاز برای رعایت rate limit"""
        while True:
            allowed, wait_time = await self.check_rate_limit(key, limit)
            if allowed:
                break
            
            logger.debug(f"Rate limit reached for {key}, waiting {wait_time:.2f}s")
            await asyncio.sleep(wait_time)


class BroadcastQueue:
    """صف هوشمند برای ارسال پیام‌های broadcast"""
    
    def __init__(self, rate_limiter: RateLimiter):
        self.rate_limiter = rate_limiter
        self.queue: asyncio.Queue = asyncio.Queue()
        self.failed_messages: List[Dict] = []
        self.success_count = 0
        self.fail_count = 0
        self.is_running = False
        
    async def add_message(self, user_id: int, send_func: Callable, *args, **kwargs):
        """اضافه کردن پیام به صف"""
        await self.queue.put({
            'user_id': user_id,
            'send_func': send_func,
            'args': args,
            'kwargs': kwargs,
            'retry_count': 0
        })
    
    async def process_queue(self):
        """پردازش صف پیام‌ها"""
        self.is_running = True
        
        while not self.queue.empty() or self.is_running:
            try:
                # دریافت پیام از صف (با timeout)
                try:
                    message = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    if self.queue.empty():
                        break
                    continue
                
                # رعایت rate limit
                await self.rate_limiter.wait_if_needed('broadcast')
                
                # ارسال پیام
                try:
                    await message['send_func'](*message['args'], **message['kwargs'])
                    self.success_count += 1
                    logger.debug(f"Message sent to user {message['user_id']}")
                    
                except Exception as e:
                    self.fail_count += 1
                    message['retry_count'] += 1
                    message['error'] = str(e)
                    
                    # تلاش مجدد برای خطاهای موقت
                    if message['retry_count'] < 3 and self._is_retryable_error(e):
                        await asyncio.sleep(2 ** message['retry_count'])  # Exponential backoff
                        await self.queue.put(message)
                        logger.warning(f"Retrying message to user {message['user_id']} (attempt {message['retry_count']})")
                    else:
                        self.failed_messages.append(message)
                        logger.error(f"Failed to send message to user {message['user_id']}: {e}")
                
            except Exception as e:
                logger.error(f"Error in broadcast queue processing: {e}")
        
        self.is_running = False
    
    def _is_retryable_error(self, error: Exception) -> bool:
        """تشخیص خطاهای قابل تلاش مجدد"""
        error_str = str(error).lower()
        retryable_keywords = ['timeout', 'network', 'connection', 'rate']
        return any(keyword in error_str for keyword in retryable_keywords)
    
    def get_stats(self) -> Dict:
        """دریافت آمار ارسال"""
        return {
            'success': self.success_count,
            'failed': self.fail_count,
            'pending': self.queue.qsize(),
            'failed_users': [msg['user_id'] for msg in self.failed_messages]
        }
    
    async def stop(self):
        """متوقف کردن پردازش صف"""
        self.is_running = False
        
        # صبر برای اتمام پردازش پیام‌های موجود
        timeout = 30  # حداکثر 30 ثانیه صبر
        start_time = time.time()
        
        while not self.queue.empty() and (time.time() - start_time) < timeout:
            await asyncio.sleep(1)
        
        if not self.queue.empty():
            logger.warning(f"Stopped with {self.queue.qsize()} messages in queue")


# Instance سراسری
rate_limiter = RateLimiter()


def rate_limit_decorator(key: str = None, calls: int = 30, period: int = 1):
    """Decorator برای اعمال rate limiting به توابع"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            limit_key = key or func.__name__
            limit = RateLimit(calls=calls, period=period)
            
            await rate_limiter.wait_if_needed(limit_key, limit)
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


class SimpleRateLimiter:
    """
    Simple Rate Limiter برای استفاده ساده
    برای سیستم User Attachments
    """
    def __init__(self, max_requests: int, window: int):
        """
        Args:
            max_requests: حداکثر تعداد درخواست
            window: بازه زمانی (ثانیه)
        """
        self.max_requests = max_requests
        self.window = window
        self.requests: Dict[int, deque] = {}  # user_id -> [timestamps]
    
    def is_allowed(self, user_id: int) -> bool:
        """
        بررسی اینکه آیا کاربر مجاز به درخواست است
        
        Args:
            user_id: شناسه کاربر
        
        Returns:
            True اگر مجاز باشد، False در غیر این صورت
        """
        current_time = time.time()
        
        # ایجاد تاریخچه برای کاربر در صورت نیاز
        if user_id not in self.requests:
            self.requests[user_id] = deque()
        
        user_requests = self.requests[user_id]
        
        # پاکسازی درخواست‌های قدیمی
        cutoff_time = current_time - self.window
        while user_requests and user_requests[0] < cutoff_time:
            user_requests.popleft()
        
        # بررسی محدودیت
        if len(user_requests) >= self.max_requests:
            return False
        
        # ثبت درخواست جدید
        user_requests.append(current_time)
        return True
    
    def get_remaining_time(self, user_id: int) -> float:
        """
        محاسبه زمان باقی‌مانده تا درخواست بعدی
        
        Args:
            user_id: شناسه کاربر
        
        Returns:
            زمان باقی‌مانده (ثانیه)
        """
        if user_id not in self.requests:
            return 0
        
        user_requests = self.requests[user_id]
        if not user_requests:
            return 0
        
        current_time = time.time()
        cutoff_time = current_time - self.window
        
        # پاکسازی درخواست‌های قدیمی
        while user_requests and user_requests[0] < cutoff_time:
            user_requests.popleft()
        
        if len(user_requests) < self.max_requests:
            return 0
        
        # محاسبه زمان تا آزاد شدن قدیمی‌ترین درخواست
        oldest_request = user_requests[0]
        remaining = self.window - (current_time - oldest_request)
        return max(0, remaining)
