"""
Application Factory Pattern

⚠️ این فایل setup_handlers() را از main.py به ساختار modular تبدیل می‌کند
⚠️ هیچ logic تغییر نکرده - فقط ساختار بهتر شده است
"""

import os
import logging
from telegram.ext import Application, ApplicationBuilder

from config.config import BOT_TOKEN, ADMIN_IDS
from core.database.database_adapter import get_database_adapter, DatabaseMode

# Import registries
from .registry.user_registry import UserHandlerRegistry
from .registry.admin_registry import AdminHandlerRegistry
from .registry.contact_registry import ContactHandlerRegistry
from .registry.other_handlers_registry import OtherHandlersRegistry
from .registry.inline_registry import InlineHandlerRegistry


logger = logging.getLogger(__name__)


class BotApplicationFactory:
    """
    Factory برای ساخت و راه‌اندازی Telegram Application
    
    ⚠️ این کلاس setup_handlers() را از CODMAttachmentsBot جدا می‌کند
    ⚠️ منطق دقیقاً یکسان است، فقط سازماندهی بهتر شده
    """
    
    def __init__(self, bot_instance):
        """
        Args:
            bot_instance: Instance of CODMAttachmentsBot
        """
        self.bot = bot_instance
        self.application = None
        self.db = bot_instance.db
    
    def create_application(self, post_init_callback=None, post_shutdown_callback=None):
        """
        ساخت Application با تمام تنظیمات - کپی از main.py خط 982-997
        
        Args:
            post_init_callback: تابع post_init
            post_shutdown_callback: تابع post_shutdown
            
        Returns:
            Application: Telegram Application آماده
        """
        logger.info("Building Telegram Application...")
        
        # ساخت Application - دقیقاً مثل main.py
        builder = ApplicationBuilder().token(BOT_TOKEN)
        
        if post_init_callback:
            builder = builder.post_init(post_init_callback)
        
        if post_shutdown_callback:
            builder = builder.post_shutdown(post_shutdown_callback)
        
        self.application = builder.build()
        
        # ذخیره database در bot_data برای دسترسی در هندلرها - main.py خط 993-994
        self.application.bot_data['database'] = self.db
        self.application.bot_data['admins'] = ADMIN_IDS
        # نقاط مشترک: استفاده مجدد از admin_handlers و role_manager برای جلوگیری از init های تکراری
        try:
            self.application.bot_data['admin_handlers'] = getattr(self.bot, 'admin_handlers', None)
            if getattr(self.bot, 'admin_handlers', None) and hasattr(self.bot.admin_handlers, 'role_manager'):
                self.application.bot_data['role_manager'] = self.bot.admin_handlers.role_manager
        except Exception:
            pass
        
        logger.info("Application built successfully")
        return self.application
    
    def setup_handlers(self):
        """
        راه‌اندازی تمام handlers - جایگزین setup_handlers() در main.py
        
        ⚠️ این تابع دقیقاً همان کار setup_handlers() قدیمی را انجام می‌دهد
        ⚠️ فقط از registries استفاده می‌کند به جای کد inline
        """
        if not self.application:
            raise RuntimeError("Application must be created first. Call create_application()")
        
        logger.info("Setting up handlers...")
        
        # ثبت User handlers - کپی از main.py خط 121-176
        logger.info("Registering user handlers...")
        user_registry = UserHandlerRegistry(self.application, self.db, self.bot)
        user_registry.register()
        
        # ثبت Admin handlers - کپی از main.py خط 178-676
        logger.info("Registering admin handlers...")
        admin_registry = AdminHandlerRegistry(self.application, self.db, self.bot)
        admin_registry.register()
        
        # ثبت Contact handlers - کپی از main.py خط 678-729
        logger.info("Registering contact handlers...")
        contact_registry = ContactHandlerRegistry(self.application, self.db, self.bot)
        contact_registry.register()
        
        # ثبت Other handlers (channel, user_attachments, tracking, error) - main.py خط 731-848
        logger.info("Registering other handlers (channel, attachments, tracking)...")
        other_registry = OtherHandlersRegistry(self.application, self.db, self.bot)
        other_registry.register()
        inline_registry = InlineHandlerRegistry(self.application, self.db, self.bot)
        inline_registry.register()

        logger.info(" All handlers registered successfully")
    
    def build_and_setup(self, post_init_callback=None, post_shutdown_callback=None):
        """
        ساخت Application و setup handlers در یک تابع
        
        این تابع ترکیب create_application() و setup_handlers() است
        
        Args:
            post_init_callback: تابع post_init
            post_shutdown_callback: تابع post_shutdown
            
        Returns:
            Application: Telegram Application آماده با handlers
        """
        self.create_application(post_init_callback, post_shutdown_callback)
        self.setup_handlers()
        return self.application
