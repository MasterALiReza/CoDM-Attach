#!/usr/bin/env python3
"""
ربات تلگرام مدیریت اتچمنت‌های Call of Duty Mobile
نسخه 1.0
"""

import logging
import signal
import sys
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters
)

# Additional imports
from config.config import BOT_TOKEN, ADMIN_IDS, BACKUP_DIR
from core.database.database_adapter import get_database_adapter
from handlers.admin.admin_handlers_modular import AdminHandlers
from core.cache.cache_manager import cache_cleanup_task
from managers.notification_scheduler import NotificationScheduler
from managers.backup_scheduler import BackupScheduler
from handlers.contact.contact_handlers import ContactHandlers
from utils.subscribers_pg import SubscribersPostgres as Subscribers
from utils.error_handler import ErrorHandler

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize error handler
error_handler = ErrorHandler()


class CODMAttachmentsBot:
    """کلاس اصلی ربات مدیریت اتچمنت‌های CODM"""
    
    def __init__(self):
        """راه‌اندازی اولیه ربات"""
        self.db = get_database_adapter()
        self.admin_handlers = AdminHandlers(self.db)
        self.contact_handlers = ContactHandlers(self.db)  # Initialize ContactHandlers
        self.notification_scheduler = NotificationScheduler(self.db)
        self.backup_scheduler = BackupScheduler(self.db)
        self.notification_manager = None  # Will be initialized later if needed
        self.application = None
        self.is_shutting_down = False
        logger.info("CODMAttachmentsBot initialized")
    
    def setup_handlers(self):
        """
        راه‌اندازی هندلرهای ربات
        
        این تابع الان از Factory Pattern استفاده می‌کند
        تمام handler registrations به app/registry/ منتقل شده‌اند
        منطق دقیقاً یکسان است - فقط ساختار بهتر شده
        
        قبل: 730+ خط handler registration در این تابع
        بعد: 5 خط - استفاده از Factory و Registries
        """
        from app.factory import BotApplicationFactory
        
        factory = BotApplicationFactory(self)
        factory.application = self.application  # استفاده از application موجود
        factory.setup_handlers()  # تمام registrations را انجام می‌دهد (کپی دقیق از کد قبلی)
    
    async def show_user_id(self, update: Update, context):
        """نمایش آیدی کاربر برای دیباگ"""
        user_id = update.effective_user.id
        is_admin = user_id in ADMIN_IDS
        
        text = f"🆔 آیدی شما: `{user_id}`\n"
        text += f"👤 نام: {update.effective_user.first_name}\n"
        if update.effective_user.username:
            text += f"📝 یوزرنیم: @{update.effective_user.username}\n"
        text += f"\n🔐 وضعیت ادمین: {'✅ بله' if is_admin else '❌ خیر'}\n"
        text += f"\n📋 لیست ادمین‌ها:\n"
        for admin_id in ADMIN_IDS:
            text += f"• `{admin_id}`\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    async def handle_error(self, update: Update, context):
        """مدیریت خطاها با سیستم جدید"""
        await error_handler.handle_telegram_error(update, context, context.error)

    async def track_user_interaction(self, update: Update, context):
        """
        رهگیری تعامل کاربر برای به‌روزرسانی last_seen
        این متد برای تمام پیام‌ها و callbackها فراخوانی می‌شود
        """
        if not update.effective_user:
            return
            
        user = update.effective_user
        try:
            # به‌روزرسانی یا ایجاد کاربر در دیتابیس
            # از متد set_user_language استفاده می‌کنیم که upsert انجام می‌دهد
            # اما چون فقط می‌خواهیم last_seen آپدیت شود، شاید بهتر باشد متد اختصاصی داشته باشیم
            # فعلاً برای سادگی، اگر کاربر جدید باشد ثبت می‌شود
            
            # اگر متد update_last_seen داریم استفاده کنیم، وگرنه ساده رد می‌شویم
            if hasattr(self.db, 'update_user_activity'):
                self.db.update_user_activity(user.id, user.username, user.first_name)
            elif hasattr(self.db, 'upsert_user'):
                 self.db.upsert_user(user.id, user.username, user.first_name)
            else:
                # Fallback: استفاده از کوئری مستقیم اگر متد خاصی نیست
                # اما چون db ما proxy است، بهتر است متد اضافه کنیم یا نادیده بگیریم
                # فعلاً فقط لاگ می‌کنیم تا برنامه کرش نکند
                pass
                
        except Exception as e:
            logger.warning(f"Failed to track user interaction: {e}")
    
    async def post_init(self, application):
        """اجرا بعد از راه‌اندازی ربات"""
        logger.info("CODM Attachments Bot started successfully!")
        # Start notification scheduler
        try:
            await self.notification_scheduler.start(application)
            logger.info("Notification scheduler started in post_init")
        except Exception as e:
            logger.error(f"Failed to start notification scheduler: {e}")
        # Start backup scheduler
        try:
            await self.backup_scheduler.start(application)
            # Store scheduler in bot_data for handlers
            application.bot_data['backup_scheduler'] = self.backup_scheduler
            logger.info("Backup scheduler started in post_init")
        except Exception as e:
            logger.error(f"Failed to start backup scheduler: {e}")
        # Start Cache Cleanup Task for periodic cache expiration cleanup
        try:
            asyncio.create_task(cache_cleanup_task())
            logger.info("Cache cleanup task started in post_init")
        except Exception as e:
            logger.warning(f"Failed to start cache cleanup task: {e}")
    
    async def cleanup(self):
        """
        پاکسازی منابع و بستن کانکشن‌ها
        این متد باید idempotent باشد (چند بار صدا زدنش مشکلی ایجاد نکند)
        """
        if self.is_shutting_down:
            return
            
        self.is_shutting_down = True
        logger.info("🛑 Initiating graceful cleanup...")
        
        try:
            # 1. Stop scheduler
            if hasattr(self, 'notification_scheduler') and self.notification_scheduler:
                try:
                    await self.notification_scheduler.stop()
                    logger.info("✅ Notification scheduler stopped")
                except Exception as e:
                    logger.warning(f"Failed to stop notification scheduler: {e}")

            # 1.5. Stop backup scheduler
            if hasattr(self, 'backup_scheduler') and self.backup_scheduler:
                try:
                    if hasattr(self.application, 'job_queue'):
                        await self.backup_scheduler.stop(self.application)
                        logger.info("✅ Backup scheduler stopped")
                except Exception as e:
                    logger.warning(f"Failed to stop backup scheduler: {e}")

            # 2. Flush pending notifications
            if hasattr(self, 'notification_manager') and self.notification_manager:
                try:
                    logger.info("📤 Flushing pending notifications...")
                    await asyncio.wait_for(
                        self.notification_manager.process_pending_notifications(),
                        timeout=5.0
                    )
                    logger.info("✅ Notifications flushed")
                except asyncio.TimeoutError:
                    logger.warning("⚠️ Notification flush timed out")
                except Exception as e:
                    logger.error(f"❌ Error flushing notifications: {e}")
            
            # 3. Close database connections
            if hasattr(self, 'db') and self.db:
                try:
                    if hasattr(self.db, 'close'):
                        self.db.close()
                        logger.info("✅ Database pool closed")
                except Exception as e:
                    logger.error(f"❌ Error closing database: {e}")
            
            # 4. Stop the application if running
            if self.application and self.application.running:
                try:
                    logger.info("🛑 Stopping application...")
                    await self.application.stop()
                    logger.info("✅ Application stopped")
                except Exception as e:
                    logger.error(f"❌ Error stopping application: {e}")
            
            logger.info("✅ Cleanup completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")

    async def post_shutdown(self, application):
        """تابع اجرایی بعد از shutdown application"""
        logger.info("Application shutdown hook called")
        await self.cleanup()
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        signal_name = signal.Signals(signum).name
        logger.info(f"🛑 Received {signal_name} signal")
        
        # Schedule cleanup
        if self.application:
            loop = asyncio.get_event_loop()
            loop.create_task(self.cleanup())
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        # Windows supports SIGINT and SIGBREAK
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # SIGTERM is available on Windows but less common
        try:
            signal.signal(signal.SIGTERM, self.signal_handler)
        except AttributeError:
            pass  # SIGTERM not available on this platform
        
        logger.info("✅ Signal handlers configured")
    
    def run(self):
        """اجرای ربات"""
        logger.info("Starting bot...")
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # ساخت Application
        from telegram.ext import ApplicationBuilder
        self.application = (
            ApplicationBuilder()
            .token(BOT_TOKEN)
            .post_init(self.post_init)
            .post_shutdown(self.post_shutdown)
            .build()
        )
        
        # ذخیره database در bot_data برای دسترسی در هندلرها
        self.application.bot_data['database'] = self.db
        self.application.bot_data['admins'] = ADMIN_IDS
        self.application.bot_data['admin_handlers'] = self.admin_handlers
        if hasattr(self.admin_handlers, 'role_manager'):
            self.application.bot_data['role_manager'] = self.admin_handlers.role_manager
        
        # setup handlers
        self.setup_handlers()
        
        # اجرای ربات
        logger.info("Bot is ready to receive messages...")
        try:
            self.application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                close_loop=False  # We'll handle loop closure
            )
        except KeyboardInterrupt:
            logger.info("🛑 KeyboardInterrupt received")
        finally:
            # Cleanup
            loop = asyncio.get_event_loop()
            if not self.is_shutting_down:
                loop.run_until_complete(self.cleanup())

def main():
    """تابع اصلی"""
    try:
        bot = CODMAttachmentsBot()
        # Ensure an event loop exists
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        bot.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise

if __name__ == "__main__":
    main()
