"""
Admin User Attachments Package
مدیریت اتچمنت‌های کاربران توسط ادمین
"""

from .review_handler import (
    show_ua_admin_menu,
    ua_admin_handlers,
    reject_conv_handler
)
from .stats_handler import stats_handlers
from .banned_handler import banned_handlers
from .reports_handler import reports_handlers
from .settings_handler import settings_handlers
from .manage_handler import manage_handlers

# ترکیب تمام handlers
all_ua_admin_handlers = (
    ua_admin_handlers + 
    stats_handlers + 
    banned_handlers + 
    reports_handlers + 
    settings_handlers +
    manage_handlers
)

__all__ = [
    'show_ua_admin_menu',
    'ua_admin_handlers',
    'reject_conv_handler',
    'stats_handlers',
    'banned_handlers',
    'reports_handlers',
    'settings_handlers',
    'manage_handlers',
    'all_ua_admin_handlers'
]
