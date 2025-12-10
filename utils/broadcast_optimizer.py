"""
سیستم Broadcast بهینه شده برای ارسال سریع به تعداد زیاد کاربر
"""

import asyncio
from typing import List, Callable, Any
from dataclasses import dataclass
from datetime import datetime
from utils.logger import get_logger

logger = get_logger('broadcast', 'broadcast.log')


@dataclass
class BroadcastTask:
    """یک task ارسال پیام"""
    user_id: int
    send_func: Callable
    args: tuple
    kwargs: dict
    retry_count: int = 0
    max_retries: int = 2


class OptimizedBroadcaster:
    """
    سیستم broadcast بهینه شده با:
    - ارسال موازی (concurrent)
    - Retry logic هوشمند
    - Rate limiting خودکار
    - Progress tracking
    """
    
    def __init__(self, max_concurrent: int = 30, delay_between_batches: float = 1.0):
        """
        Args:
            max_concurrent: تعداد maximum ارسال همزمان (Telegram limit: 30/sec)
            delay_between_batches: تاخیر بین هر batch (ثانیه)
        """
        self.max_concurrent = max_concurrent
        self.delay_between_batches = delay_between_batches
        self.success_count = 0
        self.fail_count = 0
        self.blocked_users = []
        self.failed_users = []  # non-blocked failures
        
    async def broadcast_to_users(
        self,
        user_ids: List[int],
        send_func: Callable,
        *args,
        **kwargs
    ) -> dict:
        """
        ارسال پیام به لیست کاربران به صورت موازی و بهینه
        
        Args:
            user_ids: لیست user ID ها
            send_func: تابع async برای ارسال (مثل context.bot.send_message)
            *args, **kwargs: آرگومان‌های تابع ارسال
        
        Returns:
            dict با آمار ارسال: {success, failed, blocked_users, duration}
        """
        start_time = datetime.now()
        self.success_count = 0
        self.fail_count = 0
        self.blocked_users = []
        self.failed_users = []
        
        total_users = len(user_ids)
        logger.info(f"Starting broadcast to {total_users} users")
        
        # تقسیم کاربران به batch های کوچکتر
        batches = [
            user_ids[i:i + self.max_concurrent]
            for i in range(0, len(user_ids), self.max_concurrent)
        ]
        
        for batch_num, batch in enumerate(batches, 1):
            logger.info(f"Processing batch {batch_num}/{len(batches)} ({len(batch)} users)")
            
            # ایجاد tasks برای این batch
            tasks = [
                self._send_to_user(user_id, send_func, *args, **kwargs)
                for user_id in batch
            ]
            
            # اجرای موازی
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # تاخیر بین batch ها (به جز batch آخر)
            if batch_num < len(batches):
                await asyncio.sleep(self.delay_between_batches)
            
            # Log progress
            progress = (batch_num / len(batches)) * 100
            logger.info(
                f"Progress: {progress:.1f}% | "
                f"Success: {self.success_count} | "
                f"Failed: {self.fail_count}"
            )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        stats = {
            'success': self.success_count,
            'failed': self.fail_count,
            'blocked_users': self.blocked_users,
            'failed_users': self.failed_users,
            'total': total_users,
            'duration_seconds': round(duration, 2),
            'rate_per_second': round(total_users / duration, 2) if duration > 0 else 0
        }
        
        logger.info(
            f"Broadcast completed: {self.success_count}/{total_users} successful "
            f"in {duration:.2f}s ({stats['rate_per_second']}/s)"
        )
        
        return stats
    
    async def _send_to_user(
        self,
        user_id: int,
        send_func: Callable,
        *args,
        **kwargs
    ):
        """ارسال پیام به یک کاربر با retry logic"""
        
        retry_count = 0
        max_retries = 2
        
        while retry_count <= max_retries:
            try:
                # اضافه کردن chat_id به kwargs
                kwargs['chat_id'] = user_id
                
                # ارسال پیام
                await send_func(*args, **kwargs)
                
                self.success_count += 1
                logger.debug(f"✓ Sent to user {user_id}")
                return
                
            except Exception as e:
                error_str = str(e).lower()
                
                # اگر کاربر بات را block کرده یا حذف کرده
                if any(keyword in error_str for keyword in ['blocked', 'user is deactivated', 'chat not found']):
                    self.blocked_users.append(user_id)
                    self.fail_count += 1
                    logger.warning(f"✗ User {user_id} blocked/deactivated bot")
                    return
                
                # خطاهای موقت که قابل retry هستند
                elif any(keyword in error_str for keyword in ['timeout', 'network', 'too many requests']):
                    retry_count += 1
                    if retry_count <= max_retries:
                        wait_time = 2 ** retry_count  # Exponential backoff
                        logger.warning(
                            f"⚠ Temporary error for user {user_id}, "
                            f"retrying in {wait_time}s (attempt {retry_count}/{max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                
                # خطای ناشناخته
                self.fail_count += 1
                # track failed user for potential fallback by caller
                try:
                    self.failed_users.append(user_id)
                except Exception:
                    pass
                logger.error(f"✗ Failed to send to user {user_id}: {e}")
                return


# Helper functions برای استفاده آسان

async def broadcast_message(
    context,
    user_ids: List[int],
    text: str,
    **kwargs
) -> dict:
    """
    ارسال سریع پیام متنی به لیست کاربران
    
    مثال:
        stats = await broadcast_message(
            context,
            [123, 456, 789],
            "سلام! این یک پیام تستی است",
            parse_mode='Markdown'
        )
        print(f"Sent to {stats['success']} users")
    """
    broadcaster = OptimizedBroadcaster()
    return await broadcaster.broadcast_to_users(
        user_ids,
        context.bot.send_message,
        text=text,
        **kwargs
    )


async def broadcast_photo(
    context,
    user_ids: List[int],
    photo,
    caption: str = None,
    **kwargs
) -> dict:
    """ارسال سریع تصویر به لیست کاربران"""
    broadcaster = OptimizedBroadcaster()
    return await broadcaster.broadcast_to_users(
        user_ids,
        context.bot.send_photo,
        photo=photo,
        caption=caption,
        **kwargs
    )


class BroadcastProgress:
    """
    نمایش progress bar برای broadcast
    
    مثال:
        progress = BroadcastProgress(1000)
        async for batch in progress.broadcast_batches(user_ids, 30):
            # ارسال به batch
            ...
            progress.update(len(batch))
    """
    
    def __init__(self, total: int):
        self.total = total
        self.current = 0
        self.success = 0
        self.failed = 0
    
    def update(self, count: int, success: int, failed: int):
        """به‌روزرسانی progress"""
        self.current += count
        self.success += success
        self.failed += failed
        
        percentage = (self.current / self.total) * 100
        logger.info(
            f"📊 Broadcast Progress: {percentage:.1f}% "
            f"({self.current}/{self.total}) | "
            f"✓ {self.success} | ✗ {self.failed}"
        )
    
    def get_summary(self) -> str:
        """دریافت خلاصه نهایی"""
        return (
            f"📈 **نتیجه ارسال:**\n"
            f"✅ موفق: {self.success}\n"
            f"❌ ناموفق: {self.failed}\n"
            f"📊 کل: {self.total}"
        )
