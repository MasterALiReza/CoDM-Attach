"""
Other Handlers Registry

⚠️ این شامل handlers دیگر است: channel, user_attachments, tracking
⚠️ تمام کدها از main.py کپی شده‌اند - هیچ logic تغییر نکرده!
"""

from telegram.ext import CallbackQueryHandler, MessageHandler, filters
from .base_registry import BaseHandlerRegistry

# Imports برای handlers
from handlers.channel.channel_handlers import get_channel_management_handler
from managers.channel_manager import check_membership_callback
from handlers.user.user_attachments import (
    user_attachment_conv_handler,
    show_user_attachments_menu,
    browse_handlers,
    my_attachments_handlers
)
from handlers.admin.user_attachments_admin import (
    show_ua_admin_menu,
    all_ua_admin_handlers,
    reject_conv_handler
)


class OtherHandlersRegistry(BaseHandlerRegistry):
    """ثبت handlers دیگر: channel, user_attachments, tracking"""
    
    def __init__(self, application, db, bot_instance):
        super().__init__(application, db)
        self.bot = bot_instance
    
    def register(self):
        """ثبت handlers - کپی دقیق از main.py"""
        self._register_channel_handlers()
        self._register_user_attachments()
        self._register_admin_user_attachments()
        self._register_tracking()
        self._register_error_handler()
    
    def _register_channel_handlers(self):
        """ثبت channel handlers - main.py خط 731-736"""
        # هندلر مدیریت کانال‌های اجباری - باید قبل از MessageHandler عمومی باشد
        channel_handler = get_channel_management_handler()
        self.application.add_handler(channel_handler)
        
        # هندلر بررسی عضویت کانال
        self.application.add_handler(CallbackQueryHandler(check_membership_callback, pattern="^check_membership$"))
    
    def _register_user_attachments(self):
        """ثبت user attachments handlers - main.py خط 738-754"""
        # ConversationHandler برای ارسال اتچمنت
        self.application.add_handler(user_attachment_conv_handler, group=0)
        
        # Browse handlers
        for handler in browse_handlers:
            self.application.add_handler(handler, group=0)
        
        # My Attachments handlers
        for handler in my_attachments_handlers:
            self.application.add_handler(handler, group=0)
        
        # منوی اصلی اتچمنت کاربران
        self.application.add_handler(
            CallbackQueryHandler(show_user_attachments_menu, pattern="^ua_menu$"),
            group=0
        )
    
    def _register_admin_user_attachments(self):
        """ثبت admin user attachments handlers - main.py خط 756-763"""
        # ConversationHandler برای رد اتچمنت (باید قبل از handlers اضافه شود)
        self.application.add_handler(reject_conv_handler, group=1)
        
        # تمام Handlers برای مدیریت اتچمنت کاربران توسط ادمین
        # شامل: review, stats, banned, reports, settings
        for handler in all_ua_admin_handlers:
            self.application.add_handler(handler, group=1)
    
    def _register_tracking(self):
        """ثبت tracking handlers - main.py خط 843-845"""
        # رهگیری تمام تعاملات برای ثبت کاربر به عنوان شناخته‌شده
        self.application.add_handler(MessageHandler(filters.ALL, self.bot.track_user_interaction), group=1)
        self.application.add_handler(CallbackQueryHandler(self.bot.track_user_interaction, pattern=".*"), group=1)
    
    def _register_error_handler(self):
        """ثبت error handler - main.py خط 848"""
        self.application.add_error_handler(self.bot.handle_error)
