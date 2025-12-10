"""
مدیریت دسته‌بندی‌ها
⚠️ این کد عیناً از user_handlers.py خط 372-416 کپی شده
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.config import WEAPON_CATEGORIES, CATEGORY_SETTINGS, GAME_MODES
from managers.channel_manager import require_channel_membership
from utils.logger import log_user_action
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text
from handlers.user.base_user_handler import BaseUserHandler


class CategoryHandler(BaseUserHandler):
    """مدیریت دسته‌بندی سلاح‌ها"""
    
    @require_channel_membership
    @log_user_action("show_mode_selection_msg")
    async def show_mode_selection_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش انتخاب مود (MP/BR) قبل از نمایش دسته‌ها - از طریق پیام"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        keyboard = [
            # دو دکمه در یک ردیف (MP در راست، BR در چپ برای RTL)
            [
                InlineKeyboardButton(t("mode.br_btn", lang), callback_data="mode_br"),
                InlineKeyboardButton(t("mode.mp_btn", lang), callback_data="mode_mp")
            ],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            t("mode.choose", lang),
            reply_markup=reply_markup
        )
    
    @require_channel_membership
    @log_user_action("show_mode_selection")
    async def show_mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش انتخاب مود (MP/BR) قبل از نمایش دسته‌ها - از طریق callback"""
        query = update.callback_query
        await query.answer()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        keyboard = [
            # دو دکمه در یک ردیف (MP در راست، BR در چپ برای RTL)
            [
                InlineKeyboardButton(t("mode.br_btn", lang), callback_data="mode_br"),
                InlineKeyboardButton(t("mode.mp_btn", lang), callback_data="mode_mp")
            ],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message_text(
            query,
            t("mode.choose", lang),
            reply_markup=reply_markup
        )
    
    @require_channel_membership
    @log_user_action("mode_selected")
    async def mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ذخیره مود انتخابی و نمایش دسته‌ها"""
        query = update.callback_query
        await query.answer()
        
        # استخراج mode از callback_data
        mode = query.data.replace("mode_", "")  # mp یا br
        context.user_data['selected_mode'] = mode
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_name = t(f"mode.{mode}_btn", lang)
        
        # فیلتر کردن دسته‌های فعال برای mode انتخاب شده
        from config.config import is_category_enabled
        active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() 
                            if is_category_enabled(k, mode)}
        
        # ساخت کیبورد 2 ستونی با نمایش تعداد
        from config import build_category_keyboard
        keyboard = build_category_keyboard(active_categories, "cat_", show_count=True, db=self.db, lang=lang)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="categories")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await safe_edit_message_text(
            query,
            f"📍 {t('mode.label', lang)}: {mode_name}\n\n{t('category.choose', lang)}",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    @require_channel_membership
    @log_user_action("show_categories_msg")

    async def show_categories_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش دسته‌بندی سلاح‌ها از طریق پیام - DEPRECATED: استفاده از show_mode_selection_msg"""
        from datetime import datetime
        
        # فیلتر کردن دسته‌های فعال - از mode ذخیره شده یا پیش‌فرض mp
        from config.config import is_category_enabled
        mode = context.user_data.get('selected_mode', 'mp')
        active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() 
                            if is_category_enabled(k, mode)}
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        # ساخت کیبورد 2 ستونی با نمایش تعداد
        from config import build_category_keyboard
        keyboard = build_category_keyboard(active_categories, "cat_", show_count=True, db=self.db, lang=lang)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # اضافه کردن timestamp برای جلوگیری از duplicate detection
        now = datetime.now().strftime("%H:%M:%S")
        text = f"{t('category.choose', lang)} _{t('notification.updated', lang, time=now)}_"
        
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    @require_channel_membership
    @log_user_action("show_categories")

    async def show_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش دسته‌بندی سلاح‌ها"""
        query = update.callback_query
        await query.answer()
        
        # فیلتر کردن دسته‌های فعال - از mode ذخیره شده یا پیش‌فرض mp
        from config.config import is_category_enabled
        mode = context.user_data.get('selected_mode', 'mp')
        active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() 
                            if is_category_enabled(k, mode)}
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        # ساخت کیبورد 2 ستونی با نمایش تعداد
        from config import build_category_keyboard
        keyboard = build_category_keyboard(active_categories, "cat_", show_count=True, db=self.db, lang=lang)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            t("category.choose", lang),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
