"""
Notification Scheduler
Runs a background loop to send scheduled notifications at defined intervals.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.logger import get_logger
from utils.broadcast_optimizer import OptimizedBroadcaster
from utils.subscribers_pg import SubscribersPostgres as Subscribers

logger = get_logger('notif_scheduler', 'notification.log')


class NotificationScheduler:
    """
    Periodically checks DB for due scheduled notifications and broadcasts them.
    """

    def __init__(self, db, subscribers: Optional[Subscribers] = None):
        self.db = db
        self.subscribers = subscribers or Subscribers()
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._broadcaster = OptimizedBroadcaster(max_concurrent=30, delay_between_batches=1.0)

    async def start(self, application):
        """
        Start the scheduler loop. Safe to call multiple times.
        """
        if self._running:
            return
        self._running = True
        # Pass application to task for bot access
        self._task = asyncio.create_task(self._run_loop(application))
        logger.info("NotificationScheduler started")

    async def stop(self):
        """
        Stop the scheduler loop gracefully.
        """
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("NotificationScheduler stopped")

    async def _run_loop(self, application):
        """Main loop: check due schedules every 60 seconds."""
        # Use UTC for consistency with PostgreSQL TIMESTAMPTZ
        check_interval_seconds = 60
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                # Fetch due schedules
                due_items = self.db.get_due_scheduled_notifications(now)
                if due_items:
                    logger.info(f"Found {len(due_items)} due scheduled notifications")
                for item in due_items:
                    try:
                        await self._send_item(application, item)
                        # Compute next run
                        interval_hours = int(item.get('interval_hours') or 0)
                        next_run_at = now + timedelta(hours=interval_hours)
                        self.db.mark_schedule_sent(item['id'], now, next_run_at)
                    except Exception as e:
                        logger.error(f"Error sending scheduled notification id={item.get('id')}: {e}")
                # Sleep
                await asyncio.sleep(check_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                logger.error(f"Scheduler loop error: {loop_err}")
                # Backoff a bit to avoid tight error loop
                await asyncio.sleep(5)

    async def _send_item(self, application, item: dict):
        """
        Broadcast one scheduled item to all subscribers using OptimizedBroadcaster.
        """
        message_type = item.get('message_type', 'text')
        text = item.get('message_text') or ''
        photo_id = item.get('photo_file_id')
        parse_mode = item.get('parse_mode') or 'Markdown'

        user_ids = self.subscribers.all()
        if not user_ids:
            logger.info("No subscribers to send scheduled notification")
            return

        if message_type == 'photo' and photo_id:
            stats = await self._broadcaster.broadcast_to_users(
                user_ids,
                application.bot.send_photo,
                photo=photo_id,
                caption=text or None,
                parse_mode=parse_mode,
            )
        else:
            stats = await self._broadcaster.broadcast_to_users(
                user_ids,
                application.bot.send_message,
                text=text,
                parse_mode=parse_mode,
            )

        # Fallback: if some users failed and we used a parse_mode, try again without parse_mode
        failed_users = stats.get('failed_users', []) or []
        if failed_users and parse_mode:
            logger.info(f"Retrying without parse_mode for {len(failed_users)} users (scheduled)")
            try:
                if message_type == 'photo' and photo_id:
                    fallback_stats = await self._broadcaster.broadcast_to_users(
                        failed_users,
                        application.bot.send_photo,
                        photo=photo_id,
                        caption=text or None,
                    )
                else:
                    fallback_stats = await self._broadcaster.broadcast_to_users(
                        failed_users,
                        application.bot.send_message,
                        text=text,
                    )
                # Merge blocked users for cleanup
                bu = (stats.get('blocked_users') or []) + (fallback_stats.get('blocked_users') or [])
                stats['blocked_users'] = bu
                # Merge counts for reporting
                stats['success'] = int(stats.get('success') or 0) + int(fallback_stats.get('success') or 0)
                stats['failed'] = int(stats.get('failed') or 0) + int(fallback_stats.get('failed') or 0)
            except Exception as e:
                logger.warning(f"Fallback send failed: {e}")

        # Remove blocked users
        for uid in stats.get('blocked_users', []) or []:
            try:
                self.subscribers.remove(uid)
            except Exception:
                pass
        logger.info(
            f"Scheduled broadcast completed: {stats.get('success')}/{stats.get('total')} in {stats.get('duration_seconds')}s"
        )
