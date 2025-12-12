"""
ماژول مدیریت دسته‌بندی سلاح‌ها (Weapon Categories) - MODE-FIRST FLOW
مسئول: فعال/غیرفعال کردن و پاک‌سازی دسته‌بندی‌ها برای هر مود (MP/BR)

Architecture: Mode → Category Management Menu
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import CATEGORY_MGMT_MODE, CATEGORY_MGMT_MENU, ADMIN_MENU
from utils.logger import log_admin_action, get_logger
from config.config import WEAPON_CATEGORIES, GAME_MODES, get_category_setting, set_category_enabled
import os
from utils.language import get_user_lang
from utils.i18n import t

logger = get_logger(__name__)


class CategoryHandler(BaseAdminHandler):
    """
    مدیریت دسته‌بندی‌ها - Mode-First Flow
    
    Features:
    - انتخاب Mode (MP/BR) ابتدای flow
    - فعال/غیرفعال کردن دسته‌ها per-mode
    - پاک‌سازی اتچمنت‌ها per-mode
    - ذخیره تنظیمات در config.py
    """
    
    def __init__(self, db):
        """مقداردهی اولیه"""
        super().__init__(db)
        self.role_manager = None  # باید از بیرون set شود
    
    def set_role_manager(self, role_manager):
        """تنظیم role manager"""
        self.role_manager = role_manager
    
    # ==================== Main Menu (Mode Selection) ====================
    
    @log_admin_action("category_mgmt_menu")
    async def category_mgmt_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        منوی اصلی مدیریت دسته‌ها - انتخاب Mode
        
        Flow: Mode Selection → Category Management for that Mode
        """
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پاک کردن navigation stack
        self._clear_navigation(context)
        
        # فیلتر کردن modeها بر اساس دسترسی کاربر
        user_id = update.effective_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        
        # اگر هیچ دسترسی ندارد
        if not allowed_modes:
            await query.edit_message_text(t("common.no_permission", lang))
            return await self.admin_menu_return(update, context)
        
        text = t("admin.categories.menu.title", lang) + "\n\n" + t("admin.categories.menu.text", lang)
        
        # انتخاب Mode (BR/MP) - فقط modeهای مجاز
        keyboard = []
        mode_buttons = []
        # ترتیب: BR راست، MP چپ
        if 'br' in allowed_modes:
            mode_buttons.append(InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="cmm_br"))
        if 'mp' in allowed_modes:
            mode_buttons.append(InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="cmm_mp"))
        if mode_buttons:
            keyboard.append(mode_buttons)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_cancel")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        logger.info("Category management menu shown - Mode selection")
        return CATEGORY_MGMT_MODE
    
    # ==================== Mode Selection Handler ====================
    
    @log_admin_action("category_mode_selected")
    async def category_mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        انتخاب Mode (BR/MP) - سپس نمایش Category Management Menu
        """
        query = update.callback_query
        await query.answer()
        
        if query.data == "admin_cancel":
            # بازگشت به پنل ادمین
            return await self.admin_menu_return(update, context)
        
        mode = query.data.replace("cmm_", "")  # br یا mp
        
        # بررسی دسترسی به mode انتخاب شده
        user_id = update.effective_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if mode not in allowed_modes:
            await query.answer(t("common.no_permission", lang), show_alert=True)
            return CATEGORY_MGMT_MODE
        
        # ذخیره mode در context
        context.user_data['cat_mgmt_mode'] = mode
        
        # ذخیره state فعلی در navigation stack
        self._push_navigation(context, CATEGORY_MGMT_MODE, {})
        
        # نمایش Category Management Menu
        return await self.show_category_management_menu(update, context, mode)
    
    # ==================== Category Management Menu ====================
    
    @log_admin_action("show_category_management_menu")
    async def show_category_management_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str = None):
        """
        نمایش منوی مدیریت دسته‌ها برای mode انتخاب شده
        
        Args:
            mode: 'mp' یا 'br' - اگر None باشد، از context خوانده می‌شود
        """
        query = update.callback_query
        
        if mode is None:
            mode = context.user_data.get('cat_mgmt_mode', 'mp')
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_name = GAME_MODES.get(mode, mode)
        
        text = t("admin.categories.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.categories.title", lang) + "\n\n" + t("admin.categories.menu.desc", lang)
        
        keyboard = []
        
        # ساخت دکمه‌های 2 ستونی برای toggle
        # Category names are displayed in English from WEAPON_CATEGORIES
        toggle_buttons = []
        for key, name in WEAPON_CATEGORIES.items():
            enabled = get_category_setting(key, mode).get('enabled', True)
            toggle_label = ("✅" if enabled else "❌") + f" {WEAPON_CATEGORIES.get(key, key)}"
            toggle_buttons.append(InlineKeyboardButton(toggle_label, callback_data=f"adm_cat_toggle_{key}"))
        
        # تقسیم به ردیف‌های 2 تایی
        for i in range(0, len(toggle_buttons), 2):
            if i + 1 < len(toggle_buttons):
                keyboard.append([toggle_buttons[i], toggle_buttons[i + 1]])
            else:
                keyboard.append([toggle_buttons[i]])
        
        # جداکننده
        keyboard.append([InlineKeyboardButton(t("admin.categories.separator.clear", lang), callback_data="noop")])
        
        # دکمه‌های پاک‌سازی
        # Category names displayed in English from WEAPON_CATEGORIES
        clear_buttons = []
        for key, name in WEAPON_CATEGORIES.items():
            clear_buttons.append(InlineKeyboardButton(f"🗑 {WEAPON_CATEGORIES.get(key, key)}", callback_data=f"adm_cat_clear_{key}"))
        
        # تقسیم به ردیف‌های 2 تایی
        for i in range(0, len(clear_buttons), 2):
            if i + 1 < len(clear_buttons):
                keyboard.append([clear_buttons[i], clear_buttons[i + 1]])
            else:
                keyboard.append([clear_buttons[i]])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")])
        
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        
        logger.info(f"Category management menu shown for mode: {mode}")
        return CATEGORY_MGMT_MENU
    
    # ==================== Toggle Handler ====================
    
    @log_admin_action("category_toggle_selected")
    async def category_toggle_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        فعال/غیرفعال کردن یک دسته برای mode فعلی
        
        Callback data: cat_toggle_{category_key}
        """
        query = update.callback_query
        await query.answer()
        
        category = query.data.replace("adm_cat_toggle_", "")
        mode = context.user_data.get('cat_mgmt_mode', 'mp')
        
        # دریافت وضعیت فعلی
        current = get_category_setting(category, mode).get('enabled', True)
        
        # تغییر وضعیت
        set_category_enabled(category, not current, mode)
        
        status = "فعال" if not current else "غیرفعال"
        logger.info(f"Category {category} toggled to {status} for mode {mode}")
        
        # بازگشت به منو با refresh
        return await self.show_category_management_menu(update, context, mode)
    
    # ==================== Clear Handlers ====================
    
    @log_admin_action("category_clear_prompt")
    async def category_clear_prompt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        نمایش پیام تایید برای پاک‌سازی
        
        Callback data: cat_clear_{category_key}
        """
        query = update.callback_query
        await query.answer()
        
        category = query.data.replace("adm_cat_clear_", "")
        mode = context.user_data.get('cat_mgmt_mode', 'mp')
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_name = GAME_MODES.get(mode, mode)
        # Force English for category name
        category_name = t(f"category.{category}", 'en')
        
        # ذخیره برای مرحله confirm
        context.user_data['cat_clear_category'] = category
        
        txt = (
            t("admin.categories.header.mode", lang, mode=mode_name) + "\n\n" +
            t("admin.categories.clear.confirm.title", lang) + "\n\n" +
            t("admin.categories.clear.confirm.prompt", lang, category=category_name, mode=mode_name) + "\n\n" +
            t("admin.categories.clear.confirm.tip", lang)
        )
        
        kb = [
            [InlineKeyboardButton(t("admin.categories.clear.buttons.confirm", lang), callback_data="cat_clear_confirm")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="cat_clear_cancel")]
        ]
        
        try:
            await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        
        logger.info(f"Clear prompt shown for category: {category}, mode: {mode}")
        return CATEGORY_MGMT_MENU
    
    @log_admin_action("category_clear_confirm")
    async def category_clear_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        تایید و اجرای پاک‌سازی
        
        Callback data: cat_clear_confirm
        """
        query = update.callback_query
        await query.answer()
        
        category = context.user_data.get('cat_clear_category')
        mode = context.user_data.get('cat_mgmt_mode', 'mp')
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_name = GAME_MODES.get(mode, mode)
        # Force English for category name
        category_name = t(f"category.{category}", 'en')
        
        if not category:
            await query.edit_message_text(t("common.not_found", lang))
            return await self.show_category_management_menu(update, context, mode)
        
        # بکاپ قبل از پاک‌سازی
        backup_file = self.db.backup_database()
        
        # شمارش اتچمنت‌ها قبل از حذف
        weapons = self.db.get_weapons_in_category(category)
        total_attachments = 0
        for weapon in weapons:
            attachments = self.db.get_all_attachments(category, weapon, mode=mode)
            total_attachments += len(attachments)
        
        # پاک‌سازی برای mode مشخص
        success = self.db.clear_category(category, mode=mode)
        
        if success:
            msg = t("admin.categories.clear.success.title", lang) + "\n\n"
            msg += t("admin.categories.clear.success.summary", lang, mode=mode_name, category=category_name, count=total_attachments)
            if backup_file:
                msg += "\n" + t("admin.weapons.backup.file", lang, file=backup_file)
            logger.info(f"Category {category} cleared successfully for mode {mode}, {total_attachments} attachments, backup: {backup_file}")
        else:
            msg = t("admin.categories.clear.error", lang)
            logger.error(f"Failed to clear category: {category}, mode: {mode}")
        
        try:
            await query.edit_message_text(msg, parse_mode='Markdown')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        
        # پاک کردن user_data
        context.user_data.pop('cat_clear_category', None)
        
        # بازگشت به منو بعد از 2 ثانیه
        import asyncio
        await asyncio.sleep(2)
        return await self.show_category_management_menu(update, context, mode)
    
    @log_admin_action("category_clear_cancel")
    async def category_clear_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو عملیات پاک‌سازی"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t("common.cancelled", lang))
        
        mode = context.user_data.get('cat_mgmt_mode', 'mp')
        context.user_data.pop('cat_clear_category', None)
        
        return await self.show_category_management_menu(update, context, mode)
    
    # ==================== Navigation Handler ====================
    
    async def handle_navigation_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        مدیریت دکمه بازگشت در فلوی Category Management
        
        Note: query.answer() فقط زمانی زده می‌شود که به admin_menu_return می‌رویم
        چون category_mgmt_menu خودش answer را handle می‌کند
        """
        query = update.callback_query
        
        # pop کردن navigation stack
        nav_item = self._pop_navigation(context)
        
        if nav_item:
            prev_state = nav_item.get('state')
            
            if prev_state == CATEGORY_MGMT_MODE:
                # بازگشت به انتخاب mode (category_mgmt_menu خودش answer می‌زند)
                return await self.category_mgmt_menu(update, context)
        
        # پیش‌فرض: بازگشت به پنل ادمین (admin_menu_return answer نمی‌زند، باید اینجا بزنیم)
        await query.answer()
        return await self.admin_menu_return(update, context)
