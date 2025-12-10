"""
Base class برای تمام User Handlers
توابع مشترک و utilities
⚠️ این کد عیناً از user_handlers.py کپی شده - خط 22-89
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from utils.subscribers_pg import SubscribersPostgres as Subscribers
from utils.logger import get_logger
from utils.i18n import t

logger = get_logger('user', 'user.log')


class BaseUserHandler:
    """کلاس پایه برای تمام user handlers"""
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseAdapter instance
        """
        self.db = db
        self.subs = Subscribers()
    
    def _track_user_info(self, update: Update):
        """
        ذخیره/به‌روزرسانی اطلاعات کاربر در دیتابیس
        Safe to call multiple times - idempotent
        """
        try:
            user = update.effective_user
            self.db.upsert_user(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
        except Exception as e:
            logger.debug(f"Could not track user info for {user.id}: {e}")
            # Silent fail - not critical for user experience
    
    def _weapon_reply_keyboard(self, top_count: int, all_count: int, lang: str = 'fa') -> ReplyKeyboardMarkup:
        """ساخت کیبورد پایینی برای عملیات سلاح (i18n)"""
        keyboard = [
            [t("weapon.menu.top", lang), t("weapon.menu.all", lang)],
            [t("menu.buttons.search", lang), t("menu.buttons.back", lang)]
        ]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    def _make_two_column_keyboard(self, items, callback_prefix, add_back_button=True, back_callback="categories", lang: str = 'fa'):
        """ساخت keyboard 2 ستونی از لیست آیتم‌ها
        
        Args:
            items: لیست آیتم‌ها (str یا tuple)
            callback_prefix: prefix برای callback_data
            add_back_button: اضافه کردن دکمه بازگشت
            back_callback: callback_data برای دکمه بازگشت
        """
        keyboard = []
        
        # ساخت ردیف‌های 2 ستونی
        for i in range(0, len(items), 2):
            row = []
            # ستون اول
            item1 = items[i]
            if isinstance(item1, tuple):
                text1, data1 = item1
            else:
                text1, data1 = item1, f"{callback_prefix}{item1}"
            row.append(InlineKeyboardButton(text1, callback_data=data1))
            
            # ستون دوم (اگر وجود داشته باشد)
            if i + 1 < len(items):
                item2 = items[i + 1]
                if isinstance(item2, tuple):
                    text2, data2 = item2
                else:
                    text2, data2 = item2, f"{callback_prefix}{item2}"
                row.append(InlineKeyboardButton(text2, callback_data=data2))
            
            keyboard.append(row)
        
        # دکمه بازگشت
        if add_back_button:
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=back_callback)])
        
        return keyboard
