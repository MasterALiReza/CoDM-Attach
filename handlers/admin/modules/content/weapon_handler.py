"""
ماژول مدیریت سلاح‌ها (Weapons) - REFACTORED
مسئول: حذف و پاک‌سازی سلاح‌ها

ترتیب جدید: Mode → Category → Weapon → Action
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import (
    WEAPON_SELECT_MODE,
    WEAPON_SELECT_CATEGORY,
    WEAPON_SELECT_WEAPON,
    WEAPON_ACTION_MENU,
    WEAPON_DELETE_CONFIRM
)
from config.config import WEAPON_CATEGORIES, GAME_MODES
from utils.logger import get_logger
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text

logger = get_logger('weapon', 'admin.log')


class WeaponHandler(BaseAdminHandler):
    """
    مدیریت سلاح‌ها - Mode First Flow
    
    Features:
    - مدیریت سلاح‌های موجود
    - حذف کامل سلاح
    - پاک‌سازی mode-specific (BR/MP)
    - بکاپ خودکار قبل از حذف
    - نمایش آمار اتچمنت‌ها
    """
    
    def __init__(self, db):
        """مقداردهی اولیه"""
        super().__init__(db)
        logger.info("WeaponHandler initialized")
    
    # ==================== Main Menu ====================
    
    async def weapon_mgmt_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        منوی اصلی مدیریت سلاح‌ها - انتخاب Mode
        
        Flow: Mode → Category → Weapon → Action
        """
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پاک کردن navigation stack
        self._clear_navigation(context)
        
        # فیلتر کردن modeها بر اساس دسترسی کاربر
        user_id = update.effective_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # اگر هیچ دسترسی ندارد
        if not allowed_modes:
            await safe_edit_message_text(query, t("common.no_permission", lang))
            return await self.admin_menu_return(update, context)
        
        text = t("admin.weapons.menu.text", lang)
        
        # انتخاب Mode (BR/MP) - فقط modeهای مجاز - ترتیب: BR راست، MP چپ
        keyboard = []
        mode_buttons = []
        if 'br' in allowed_modes:
            mode_buttons.append(InlineKeyboardButton(t("mode.br_btn", lang), callback_data="wmm_br"))
        if 'mp' in allowed_modes:
            mode_buttons.append(InlineKeyboardButton(t("mode.mp_btn", lang), callback_data="wmm_mp"))
        if mode_buttons:
            keyboard.append(mode_buttons)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_cancel")])
        
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        logger.info("Weapon management menu shown - Mode selection")
        return WEAPON_SELECT_MODE
    
    # ==================== Mode Selection ====================
    
    async def weapon_mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        انتخاب Mode (BR/MP) - سپس نمایش Categories
        """
        query = update.callback_query
        await query.answer()
        
        if query.data == "admin_cancel":
            # بازگشت به پنل ادمین
            return await self.admin_menu_return(update, context)
        
        mode = query.data.replace("wmm_", "")  # br یا mp
        
        # بررسی دسترسی به mode انتخاب شده
        user_id = update.effective_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if mode not in allowed_modes:
            await query.answer(t("common.no_permission", lang), show_alert=True)
            return WEAPON_SELECT_MODE
        
        # ذخیره state فعلی
        self._push_navigation(context, WEAPON_SELECT_MODE, {})
        
        context.user_data['weapon_mgmt_mode'] = mode
        mode_name = t(f"mode.{mode}_short", lang)
        
        text = t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n"
        text += t("admin.weapons.menu.title", lang) + "\n\n"
        text += t("admin.weapons.choose_category", lang)
        
        # کیبورد دسته‌ها
        from config.config import build_category_keyboard
        keyboard = build_category_keyboard(WEAPON_CATEGORIES, "wmcat_")
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")])
        
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        logger.info(f"Mode {mode} selected for weapon management")
        return WEAPON_SELECT_CATEGORY
    
    # ==================== Category Selection ====================
    
    async def weapon_select_category_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        انتخاب دسته و نمایش سلاح‌ها
        
        Callback data: wmcat_{category}
        """
        query = update.callback_query
        await query.answer()
        
        if query.data == "nav_back":
            # بازگشت به لیست modeها
            context.user_data.pop('weapon_mgmt_category', None)
            return await self.weapon_mgmt_menu(update, context)
        
        # ذخیره state فعلی
        self._push_navigation(context, WEAPON_SELECT_CATEGORY, {
            'weapon_mgmt_mode': context.user_data.get('weapon_mgmt_mode')
        })
        
        category = query.data.replace("wmcat_", "")
        context.user_data['weapon_mgmt_category'] = category
        
        mode = context.user_data.get('weapon_mgmt_mode', 'br')
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_name = t(f"mode.{mode}_short", lang)
        
        # دریافت سلاح‌ها
        weapons = self.db.get_weapons_in_category(category)
        
        if not weapons:
            await safe_edit_message_text(
                query,
                t("admin.weapons.path", lang, mode=t(f"mode.{mode}_short", lang), category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("admin.weapons.none_in_category", lang),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")]]),
                parse_mode='Markdown'
            )
            logger.warning(f"No weapons found in category: {category}")
            return WEAPON_SELECT_CATEGORY
        
        text = t("admin.weapons.path", lang, mode=t(f"mode.{mode}_short", lang), category=WEAPON_CATEGORIES.get(category)) + "\n\n"
        text += t("weapon.choose", lang)
        
        # کیبورد سلاح‌ها
        keyboard = self._make_weapon_keyboard(weapons, "wmwpn_", category)
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")])
        
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        logger.info(f"Category {category} selected, showing {len(weapons)} weapons for mode {mode}")
        return WEAPON_SELECT_WEAPON
    
    # ==================== Weapon Selection ====================
    
    async def weapon_select_weapon_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        نمایش منوی عملیات برای سلاح انتخابی
        
        Callback data: wmwpn_{weapon}
        
        Shows:
        - آمار اتچمنت‌ها (BR/MP)
        - دکمه‌های عملیات
        """
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "nav_back":
            # بازگشت به لیست دسته‌ها
            context.user_data.pop('weapon_mgmt_weapon', None)
            mode = context.user_data.get('weapon_mgmt_mode', 'br')
            mode_name = t(f"mode.{mode}_short", lang)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            from config.config import build_category_keyboard
            keyboard = build_category_keyboard(WEAPON_CATEGORIES, "wmcat_")
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")])
            
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=t(f"mode.{mode}_short", lang)) + "\n\n" + t("admin.weapons.menu.title", lang) + "\n\n" + t("admin.weapons.choose_category", lang),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return WEAPON_SELECT_CATEGORY
        
        # ذخیره state فعلی
        self._push_navigation(context, WEAPON_SELECT_WEAPON, {
            'weapon_mgmt_mode': context.user_data.get('weapon_mgmt_mode'),
            'weapon_mgmt_category': context.user_data.get('weapon_mgmt_category')
        })
        
        weapon = query.data.replace("wmwpn_", "")
        category = context.user_data.get('weapon_mgmt_category')
        mode = context.user_data.get('weapon_mgmt_mode', 'br')
        mode_name = t(f"mode.{mode}_short", lang)
        
        context.user_data['weapon_mgmt_weapon'] = weapon
        
        # دریافت اطلاعات سلاح
        info = self.db.get_weapon_info(category, weapon)
        
        text = t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n"
        text += t("admin.weapons.weapon.header", lang, weapon=weapon) + "\n\n"
        text += t("admin.weapons.stats.title", lang) + "\n"
        text += t("admin.weapons.stats.line", lang, mode=t("mode.br_short", lang), count=info['br']['attachment_count'], top=info['br']['top_count']) + "\n"
        text += t("admin.weapons.stats.line", lang, mode=t("mode.mp_short", lang), count=info['mp']['attachment_count'], top=info['mp']['top_count']) + "\n\n"
        text += t("admin.weapons.choose_action", lang)
        
        keyboard = []
        
        # دکمه پاک‌سازی mode فعلی
        mode_count = info[mode]['attachment_count']
        if mode_count > 0:
            keyboard.append([InlineKeyboardButton(
                t("admin.weapons.buttons.clear_mode", lang, mode=mode_name, count=mode_count), 
                callback_data=f"wmact_clear_{mode}"
            )])
        
        # دکمه حذف کامل
        total_count = info['br']['attachment_count'] + info['mp']['attachment_count']
        keyboard.append([InlineKeyboardButton(
            t("admin.weapons.buttons.delete_weapon", lang, count=total_count), 
            callback_data="wmact_delete"
        )])
        
        # دکمه بازگشت
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")])
        
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        logger.info(f"Weapon {weapon} selected in mode {mode}, showing actions")
        return WEAPON_ACTION_MENU
    
    # ==================== Action Selection ====================
    
    async def weapon_action_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        پردازش عملیات انتخابی
        
        Actions:
        - delete: حذف کامل
        - clear_{mode}: پاک‌سازی mode خاص
        
        همه نیاز به تایید دارند
        """
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # بازگشت
        if query.data == "nav_back":
            return await self.handle_navigation_back(update, context)
        
        await query.answer()
        
        action = query.data.replace("wmact_", "")
        weapon = context.user_data.get('weapon_mgmt_weapon')
        category = context.user_data.get('weapon_mgmt_category')
        mode = context.user_data.get('weapon_mgmt_mode', 'br')
        mode_name = t(f"mode.{mode}_btn", lang)
        
        if action == "delete":
            # حذف کامل - نیاز به تایید
            text = (
                t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n"
                + t("admin.weapons.confirm.delete.title", lang) + "\n\n"
                + t("admin.weapons.confirm.delete.prompt", lang, weapon=weapon) + "\n\n"
                + t("admin.weapons.confirm.delete.warning", lang) + "\n"
                + t("admin.weapons.confirm.delete.tip", lang)
            )
            keyboard = [
                [InlineKeyboardButton(t("admin.weapons.buttons.confirm_delete", lang), callback_data="wmconf_delete")],
                [InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="nav_back")]
            ]
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            logger.info(f"Delete confirmation requested for weapon: {weapon}")
            return WEAPON_DELETE_CONFIRM
        
        elif action.startswith("clear_"):
            clear_mode = action.replace("clear_", "")  # br یا mp
            clear_mode_short = t(f"mode.{clear_mode}_short", lang)
            clear_mode_btn = t(f"mode.{clear_mode}_btn", lang)
            
            text = (
                t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n"
                + t("admin.weapons.confirm.clear.title", lang) + "\n\n"
                + t("admin.weapons.confirm.clear.prompt", lang, mode=clear_mode_short, weapon=weapon) + "\n\n"
                + t("admin.weapons.confirm.clear.warning", lang, mode=clear_mode_short)
            )
            keyboard = [
                [InlineKeyboardButton(t("admin.weapons.buttons.confirm_clear", lang, mode=clear_mode_btn), callback_data=f"wmconf_clear_{clear_mode}")],
                [InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="nav_back")]
            ]
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            logger.info(f"Clear {clear_mode} confirmation requested for weapon: {weapon}")
            return WEAPON_DELETE_CONFIRM
        
        return WEAPON_ACTION_MENU
    
    # ==================== Confirmation & Execution ====================
    
    async def weapon_delete_confirmed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        اجرای حذف بعد از تایید
        
        Callback data:
        - wmconf_delete: حذف کامل
        - wmconf_clear_{mode}: پاک‌سازی mode
        - nav_back: انصراف
        """
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # انصراف
        if query.data == "nav_back":
            return await self.handle_navigation_back(update, context)
        
        await query.answer()
        
        weapon = context.user_data.get('weapon_mgmt_weapon')
        category = context.user_data.get('weapon_mgmt_category')
        mode = context.user_data.get('weapon_mgmt_mode', 'br')
        mode_name = t(f"mode.{mode}_btn", lang)
        
        # بکاپ قبل از حذف
        backup_file = self.db.backup_database()
        
        if query.data == "wmconf_delete":
            # حذف کامل
            success = self.db.delete_weapon(category, weapon, mode=None)
            if success:
                msg = t("admin.weapons.delete.success", lang, weapon=weapon) + "\n"
                logger.info(f"Weapon {weapon} deleted completely")
            else:
                msg = t("admin.weapons.delete.error", lang, weapon=weapon) + "\n"
                logger.error(f"Failed to delete weapon: {weapon}")
        
        elif query.data.startswith("wmconf_clear_"):
            clear_mode = query.data.replace("wmconf_clear_", "")
            clear_mode_name = t(f"mode.{clear_mode}_short", lang)
            success = self.db.delete_weapon(category, weapon, mode=clear_mode)
            if success:
                msg = t("admin.weapons.clear.success", lang, mode=clear_mode_name, weapon=weapon) + "\n"
                logger.info(f"Weapon {weapon} cleared for mode: {clear_mode}")
            else:
                msg = t("admin.weapons.clear.error", lang, mode=clear_mode_name) + "\n"
                logger.error(f"Failed to clear weapon {weapon} for mode: {clear_mode}")
        
        # Invalidate caches if operation succeeded
        try:
            if 'success' in locals() and success:
                from core.cache.cache_manager import get_cache
                cache = get_cache()
                # Category counts and related lists
                cache.delete("category_counts")
                cache.invalidate_pattern("get_weapons_in_category")
                cache.invalidate_pattern("get_all_attachments")
                cache.invalidate_pattern("get_weapon_attachments")
                cache.invalidate_pattern("get_top_attachments")
        except Exception:
            pass

        if backup_file:
            msg += "\n" + t("admin.weapons.backup.file", lang, file=backup_file)
        
        keyboard = [[InlineKeyboardButton(t("admin.weapons.buttons.back_to_mgmt", lang), callback_data="admin_weapon_mgmt")]]
        await safe_edit_message_text(query, msg, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        # پاکسازی داده‌های موقت
        context.user_data.pop('weapon_mgmt_weapon', None)
        context.user_data.pop('weapon_mgmt_category', None)
        context.user_data.pop('weapon_mgmt_mode', None)
        
        return WEAPON_SELECT_MODE
    
    # ==================== Helper Methods ====================
    
    async def _rebuild_state_screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: int):
        """بازسازی صفحه برای هر state"""
        query = update.callback_query
        
        if state == WEAPON_SELECT_MODE:
            # بازگشت به لیست modeها
            user_id = update.effective_user.id
            allowed_modes = self.role_manager.get_mode_permissions(user_id)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            text = t("admin.weapons.menu.text", lang)
            
            keyboard = []
            mode_buttons = []
            # ترتیب: BR راست، MP چپ
            if 'br' in allowed_modes:
                mode_buttons.append(InlineKeyboardButton(t("mode.br_btn", lang), callback_data="wmm_br"))
            if 'mp' in allowed_modes:
                mode_buttons.append(InlineKeyboardButton(t("mode.mp_btn", lang), callback_data="wmm_mp"))
            if mode_buttons:
                keyboard.append(mode_buttons)
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_cancel")])
            
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        elif state == WEAPON_SELECT_CATEGORY:
            # بازگشت به لیست دسته‌ها
            mode = context.user_data.get('weapon_mgmt_mode', 'br')
            mode_name = t(f"mode.{mode}_btn", lang)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            from config.config import build_category_keyboard
            keyboard = build_category_keyboard(WEAPON_CATEGORIES, "wmcat_")
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")])
            
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.weapons.menu.title", lang) + "\n\n" + t("admin.weapons.choose_category", lang),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif state == WEAPON_SELECT_WEAPON:
            # بازسازی لیست سلاح‌ها
            await self.weapon_select_category_menu(update, context)
        
        elif state == WEAPON_ACTION_MENU:
            # بازسازی منوی عملیات
            await self.weapon_select_weapon_menu(update, context)
    
    def _make_weapon_keyboard(self, weapons: list, prefix: str, category: str) -> list:
        """
        ساخت کیبورد سلاح‌ها
        
        Args:
            weapons: لیست نام سلاح‌ها
            prefix: پیشوند callback data
            category: دسته فعلی
        
        Returns:
            لیست ردیف‌های کیبورد (2 یا 3 ستونه)
        """
        keyboard = []
        buttons = [InlineKeyboardButton(w, callback_data=f"{prefix}{w}") for w in weapons]
        
        # تعیین تعداد ستون‌ها: AR و SMG -> 3 ستون، بقیه -> 2 ستون
        if category and category.lower() in ['assault_rifle', 'smg', 'ar']:
            columns = 3
        else:
            columns = 2
        
        # تقسیم به ردیف‌ها
        for i in range(0, len(buttons), columns):
            row = buttons[i:i + columns]
            keyboard.append(row)
        
        return keyboard
