"""
Base handler برای تمام admin handlers
شامل توابع مشترک و helper methods
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from typing import Dict, List
from config.config import ADMIN_IDS, MESSAGES
from core.security.role_manager import Permission
from utils.logger import get_logger
from utils.language import get_user_lang
from utils.i18n import t

logger = get_logger('admin_base', 'admin.log')


class BaseAdminHandler:
    """کلاس پایه برای تمام admin handlers"""
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseAdapter instance
        """
        self.db = db
        
        # ایجاد role manager برای مدیریت نقش‌ها و دسترسی‌ها
        from core.security.role_manager import RoleManager
        self.role_manager = RoleManager(db)
    
    def is_admin(self, user_id: int) -> bool:
        """بررسی دسترسی ادمین"""
        if hasattr(self, 'role_manager'):
            return self.role_manager.is_admin(user_id)
        # fallback به سیستم قدیمی
        return user_id in ADMIN_IDS
    
    async def check_permission(self, user_id: int, permission) -> bool:
        """بررسی دسترسی کاربر به یک permission خاص"""
        if hasattr(self, 'role_manager'):
            return self.role_manager.has_permission(user_id, permission)
        # fallback: اگر ادمین است true برگردان
        return self.is_admin(user_id)
    
    async def send_permission_denied(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ارسال پیام عدم دسترسی"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        message = t("admin.permission.denied.title", lang) + "\n\n" + t("admin.permission.denied.body", lang)
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")]]
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_message(
                update.effective_chat.id,
                message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    async def admin_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو عملیات و بازگشت به منوی ادمین"""
        query = update.callback_query
        if query:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t("common.cancelled", lang))
        
        # Clear user data
        context.user_data.clear()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        message = t("admin.canceled_return", lang)
        
        if query:
            await query.edit_message_text(message)
        else:
            await context.bot.send_message(
                update.effective_chat.id,
                message
            )
            
        return ConversationHandler.END
    
    # ========== Navigation Stack Methods ==========
    
    def _push_navigation(self, context: ContextTypes.DEFAULT_TYPE, state: int, data: dict = None):
        """اضافه کردن یک مرحله به navigation stack"""
        if 'nav_stack' not in context.user_data:
            context.user_data['nav_stack'] = []
        context.user_data['nav_stack'].append({'state': state, 'data': data or {}})
    
    def _pop_navigation(self, context: ContextTypes.DEFAULT_TYPE):
        """برگشت به مرحله قبلی"""
        if 'nav_stack' in context.user_data and context.user_data['nav_stack']:
            return context.user_data['nav_stack'].pop()
        return None
    
    def _clear_navigation(self, context: ContextTypes.DEFAULT_TYPE):
        """پاک کردن navigation stack"""
        if 'nav_stack' in context.user_data:
            context.user_data['nav_stack'] = []
    
    def _add_back_cancel_buttons(self, keyboard: list, show_back: bool = True):
        """اضافه کردن دکمه‌های بازگشت و لغو به keyboard"""
        buttons = []
        if show_back:
            buttons.append(InlineKeyboardButton("⬅️", callback_data="nav_back"))
        buttons.append(InlineKeyboardButton("❌", callback_data="admin_cancel"))
        keyboard.append(buttons)
    
    # ========== Helper Methods ==========
    
    def _make_weapon_keyboard(self, weapons: List[str], prefix: str, category: str = None) -> List[List[InlineKeyboardButton]]:
        """
        ساخت keyboard برای لیست سلاح‌ها با تعداد ستون متغیر
        
        Args:
            weapons: لیست نام سلاح‌ها
            prefix: پیشوند برای callback_data
            category: دسته سلاح (اختیاری)
        
        Returns:
            لیست از لیست دکمه‌ها
        """
        keyboard = []
        
        # تعیین تعداد ستون‌ها
        # برای دسته‌های AR و SMG همیشه 3 ستون
        if category:
            category_lower = str(category).lower().strip()
            if category_lower in ['assault_rifle', 'smg', 'ar']:
                columns = 3
            elif len(weapons) > 0:
                # بر اساس طول نام سلاح‌ها
                max_name_length = max([len(w) for w in weapons], default=0)
                
                if max_name_length <= 8:
                    columns = 3
                elif max_name_length <= 15:
                    columns = 2
                else:
                    columns = 1
            else:
                columns = 2
        else:
            # اگر category نداریم، بر اساس طول نام سلاح‌ها
            max_name_length = max([len(w) for w in weapons], default=0)
            
            if max_name_length <= 8:
                columns = 3
            elif max_name_length <= 15:
                columns = 2
            else:
                columns = 1
        
        # ساخت ردیف‌ها
        row = []
        for weapon in weapons:
            callback_data = f"{prefix}{weapon}"
            row.append(InlineKeyboardButton(weapon, callback_data=callback_data))
            
            if len(row) == columns:
                keyboard.append(row)
                row = []
        
        # اضافه کردن ردیف آخر اگر کامل نشده
        if row:
            keyboard.append(row)
        
        return keyboard
    
    async def admin_menu_return(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بازگشت به منوی اصلی ادمین"""
        query = update.callback_query if update.callback_query else None
        
        user_id = update.effective_user.id
        lang = get_user_lang(update, context, self.db) or 'fa'
        keyboard = self._get_admin_main_keyboard(user_id, lang)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            try:
                await query.edit_message_text(
                    t("admin.panel.welcome", lang),
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception as e:
                if "message is not modified" not in str(e).lower():
                    raise
        else:
            await update.message.reply_text(
                t("admin.panel.welcome", lang),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        # پاک کردن داده‌های موقت
        self._clear_temp_data(context)
        
        # Import states from admin_states
        from handlers.admin.admin_states import ADMIN_MENU
        return ADMIN_MENU
    
    def _clear_temp_data(self, context: ContextTypes.DEFAULT_TYPE):
        """پاک کردن داده‌های موقت از context"""
        keys_to_remove = [
            'add_att_category', 'add_att_weapon', 'add_att_mode',
            'add_att_code', 'add_att_name', 'add_att_image', 'add_att_is_top',
            'del_att_category', 'del_att_weapon', 'del_att_mode',
            'set_top_category', 'set_top_weapon', 'set_top_mode',
            'edit_att_category', 'edit_att_weapon', 'edit_att_mode', 'edit_att_code',
            'notif_type', 'notif_text', 'notif_photo',
            'guide_key', 'guide_mode', 'text_key', 'tmpl_key',
            'admin_entry_handled', 'faq_question', 'edit_faq_id', 'edit_faq_data',
            'selected_admin_role', 'new_admin_id', 'edit_admin_user_id'
        ]
        for key in keys_to_remove:
            context.user_data.pop(key, None)
    
    def _get_admin_main_keyboard(self, user_id: int, lang: str = 'fa') -> List[List[InlineKeyboardButton]]:
        """
        ساخت کیبورد منوی اصلی ادمین با فیلتر دسترسی و دسته‌بندی منطقی
        
        Args:
            user_id: شناسه کاربر ادمین
        
        Returns:
            لیست دکمه‌های فیلتر شده
        
        ترتیب دکمه‌ها:
        1. مدیریت محتوای اتچمنت‌ها (افزودن، ویرایش، حذف، برترین‌ها)
        2. مدیریت محتوای کاربران (اتچمنت‌های کاربری)
        3. ساختار بازی (دسته‌ها، سلاح‌ها)
        4. تنظیمات محتوا (پیشنهادی، تنظیمات)
        5. پشتیبانی کاربران (تیکت‌ها، FAQ)
        6. ارتباطات و اعلان‌ها (ارسال، تنظیمات)
        7. مدیریت متون (ویرایش متون)
        8. مدیریت سیستم (ادمین‌ها، کانال‌ها)
        9. داده و بکاپ (import/export، backup)
        10. آمار و تحلیل (آنالیتیکس، سلامت، بازخورد)
        11. خروج
        """
        from core.security.role_manager import Permission
        
        # دریافت دسترسی‌های کاربر
        user_permissions = self.role_manager.get_user_permissions(user_id)
        
        keyboard = []
        
        # ========== 1️⃣ مدیریت محتوای اتچمنت‌ها ==========
        # ردیف اول: افزودن و ویرایش
        content_row1 = []
        if Permission.MANAGE_ATTACHMENTS_BR in user_permissions or Permission.MANAGE_ATTACHMENTS_MP in user_permissions:
            content_row1.append(InlineKeyboardButton(t("admin.buttons.add_attachment", lang), callback_data="admin_add_attachment"))
            content_row1.append(InlineKeyboardButton(t("admin.buttons.edit_attachment", lang), callback_data="admin_edit_attachment"))
        if content_row1:
            keyboard.append(content_row1)
        
        # ردیف دوم: حذف و تنظیم برترین‌ها
        content_row2 = []
        if Permission.MANAGE_ATTACHMENTS_BR in user_permissions or Permission.MANAGE_ATTACHMENTS_MP in user_permissions:
            content_row2.append(InlineKeyboardButton(t("admin.buttons.delete_attachment", lang), callback_data="admin_delete_attachment"))
            content_row2.append(InlineKeyboardButton(t("admin.buttons.set_top", lang), callback_data="admin_set_top"))
        if content_row2:
            keyboard.append(content_row2)
        
        # ========== 2️⃣ مدیریت محتوای کاربران ==========
        if Permission.MANAGE_USER_ATTACHMENTS in user_permissions or self.role_manager.is_super_admin(user_id):
            keyboard.append([
                InlineKeyboardButton(t("admin.buttons.ua_admin", lang), callback_data="ua_admin_menu")
            ])
        
        # ========== 3️⃣ ساختار بازی ==========
        structure_row = []
        if Permission.MANAGE_CATEGORIES in user_permissions:
            structure_row.append(InlineKeyboardButton(t("admin.buttons.category_mgmt", lang), callback_data="admin_category_mgmt"))
            structure_row.append(InlineKeyboardButton(t("admin.buttons.weapon_mgmt", lang), callback_data="admin_weapon_mgmt"))
        if structure_row:
            keyboard.append(structure_row)
        
        # ========== 4️⃣ تنظیمات محتوا ==========
        settings_row = []
        if Permission.MANAGE_SUGGESTED_ATTACHMENTS in user_permissions:
            settings_row.append(InlineKeyboardButton(t("admin.buttons.suggested", lang), callback_data="admin_manage_suggested"))
        if Permission.MANAGE_GUIDES_BR in user_permissions or Permission.MANAGE_GUIDES_MP in user_permissions:
            settings_row.append(InlineKeyboardButton(t("admin.buttons.game_settings", lang), callback_data="admin_guides"))
        if Permission.MANAGE_CMS in user_permissions:
            settings_row.append(InlineKeyboardButton(t("admin.buttons.cms", lang), callback_data="admin_cms"))
        if settings_row:
            keyboard.append(settings_row)
        
        # ========== 5️⃣ پشتیبانی کاربران ==========
        support_row = []
        if Permission.MANAGE_TICKETS in user_permissions:
            support_row.append(InlineKeyboardButton(t("admin.buttons.tickets", lang), callback_data="admin_tickets"))
        if Permission.MANAGE_FAQS in user_permissions:
            support_row.append(InlineKeyboardButton(t("admin.buttons.faq", lang), callback_data="admin_faqs"))
        if support_row:
            keyboard.append(support_row)
        
        # ========== 6️⃣ ارتباطات و اعلان‌ها ==========
        comm_row = []
        if Permission.SEND_NOTIFICATIONS in user_permissions:
            comm_row.append(InlineKeyboardButton(t("admin.buttons.notify_send", lang), callback_data="admin_notify"))
        if Permission.MANAGE_NOTIFICATION_SETTINGS in user_permissions:
            comm_row.append(InlineKeyboardButton(t("admin.buttons.notify_settings", lang), callback_data="admin_notify_settings"))
        if comm_row:
            keyboard.append(comm_row)
        
        # ========== 7️⃣ مدیریت متون ==========
        if Permission.MANAGE_TEXTS in user_permissions:
            keyboard.append([InlineKeyboardButton(t("admin.buttons.edit_texts", lang), callback_data="admin_texts")])
        
        # ========== 8️⃣ مدیریت سیستم ==========
        admin_row = []
        if Permission.MANAGE_ADMINS in user_permissions:
            admin_row.append(InlineKeyboardButton(t("admin.buttons.manage_admins", lang), callback_data="manage_admins"))
        if Permission.MANAGE_CHANNELS in user_permissions:
            admin_row.append(InlineKeyboardButton(t("admin.buttons.manage_channels", lang), callback_data="channel_management"))
        if admin_row:
            keyboard.append(admin_row)
        
        # ========== 9️⃣ داده و بکاپ ==========
        if Permission.IMPORT_EXPORT in user_permissions or Permission.BACKUP_DATA in user_permissions:
            keyboard.append([
                InlineKeyboardButton(t("admin.buttons.data_mgmt", lang), callback_data="admin_data_management")
            ])
        
        # ========== 🔟 آمار و تحلیل ==========
        
        # آنالیتیکس و سلامت داده
        analytics_row = []
        if Permission.VIEW_ANALYTICS in user_permissions:
            analytics_row.append(InlineKeyboardButton(t("admin.buttons.analytics", lang), callback_data="attachment_analytics"))
        if Permission.VIEW_HEALTH_REPORTS in user_permissions:
            analytics_row.append(InlineKeyboardButton(t("admin.buttons.data_health", lang), callback_data="data_health"))
        if analytics_row:
            keyboard.append(analytics_row)
        
        # داشبورد بازخورد
        if Permission.VIEW_ANALYTICS in user_permissions:
            keyboard.append([
                InlineKeyboardButton(t("admin.buttons.feedback_dashboard", lang), callback_data="fb_dashboard")
            ])
        
        # ========== 1️⃣1️⃣ خروج ==========
        keyboard.append([InlineKeyboardButton(t("admin.buttons.exit", lang), callback_data="admin_exit")])
        
        return keyboard
    
    async def data_management_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی مدیریت داده و بکاپ"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        user_permissions = self.role_manager.get_user_permissions(user_id)
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        message = t("admin.data_mgmt.title", lang) + "\n\n" + t("admin.data_mgmt.body", lang)
        
        keyboard = []
        
        # Import/Export
        if Permission.IMPORT_EXPORT in user_permissions:
            keyboard.append([
                InlineKeyboardButton(t("admin.data_mgmt.import", lang), callback_data="admin_import"),
                InlineKeyboardButton(t("admin.data_mgmt.export", lang), callback_data="admin_export")
            ])
        
        # Backup
        if Permission.BACKUP_DATA in user_permissions:
            keyboard.append([
                InlineKeyboardButton(t("admin.data_mgmt.backup", lang), callback_data="admin_backup")
            ])
        
        # بازگشت
        keyboard.append([
            InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")
        ])
        
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def handle_navigation_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت دکمه بازگشت"""
        query = update.callback_query
        # توجه: answer() قبلاً در handler caller صدا زده شده
        
        # بازیابی state قبلی
        prev = self._pop_navigation(context)
        
        if not prev:
            # اگر stack خالی است، به منوی اصلی برگرد
            return await self.admin_menu_return(update, context)
        
        state = prev['state']
        data = prev.get('data', {})
        
        # بازگرداندن داده‌ها
        for key, value in data.items():
            context.user_data[key] = value
        
        # بازسازی صفحه قبلی
        await self._rebuild_state_screen(update, context, state)
        
        return state
    
    async def _rebuild_state_screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: int):
        """
        بازسازی و نمایش صفحه مربوط به state قبلی
        این متد باید در هر handler که از navigation استفاده می‌کند override شود
        """
        # این متد در base است، اما هر handler باید آن را override کند
        pass
    
    def _create_confirmation_keyboard(
        self,
        confirm_callback: str = "confirm_yes",
        cancel_callback: str = "confirm_no",
        confirm_text: str = None,
        cancel_text: str = None,
        show_back: bool = False
    ) -> List[List[InlineKeyboardButton]]:
        """
        ساخت کیبورد تایید استاندارد
        
        Args:
            confirm_callback: callback_data برای دکمه تایید
            cancel_callback: callback_data برای دکمه لغو
            confirm_text: متن دکمه تایید
            cancel_text: متن دکمه لغو
            show_back: نمایش دکمه بازگشت
        
        Returns:
            لیست دکمه‌های کیبورد
        """
        if confirm_text is None:
            confirm_text = "✅"
        if cancel_text is None:
            cancel_text = "❌"
        keyboard = [
            [
                InlineKeyboardButton(confirm_text, callback_data=confirm_callback),
                InlineKeyboardButton(cancel_text, callback_data=cancel_callback)
            ]
        ]
        if show_back:
            keyboard.append([InlineKeyboardButton("⬅️", callback_data="nav_back")])
        keyboard.append([InlineKeyboardButton("❌", callback_data="admin_cancel")])
        return keyboard
