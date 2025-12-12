from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin.modules.base_handler import BaseAdminHandler
from utils.language import get_user_lang
from utils.i18n import t
from core.security.role_manager import Permission

class AttachmentManagementHandler(BaseAdminHandler):
    """مدیریت منوی اصلی اتچمنت‌ها"""
    
    async def attachment_management_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی مدیریت اتچمنت‌ها"""
        query = update.callback_query
        try:
            await query.answer()
        except:
            pass
            
        user_id = update.effective_user.id
        lang = get_user_lang(update, context, self.db) or 'fa'
        user_permissions = self.role_manager.get_user_permissions(user_id)
        
        # عنوان منو
        message = t("admin.menu.attachments", lang) + "\n\n" + t("admin.panel.welcome", lang).split('\n')[-1]
        
        keyboard = []
        
        # ردیف ۱: افزودن و ویرایش (پرکاربردترین‌ها)
        row1 = []
        if Permission.MANAGE_ATTACHMENTS_BR in user_permissions or Permission.MANAGE_ATTACHMENTS_MP in user_permissions:
            row1.append(InlineKeyboardButton(t("admin.buttons.add_attachment", lang), callback_data="admin_add_attachment"))
            row1.append(InlineKeyboardButton(t("admin.buttons.edit_attachment", lang), callback_data="admin_edit_attachment"))
        if row1:
            keyboard.append(row1)
            
        # ردیف ۲: حذف و برترین‌ها
        row2 = []
        if Permission.MANAGE_ATTACHMENTS_BR in user_permissions or Permission.MANAGE_ATTACHMENTS_MP in user_permissions:
            row2.append(InlineKeyboardButton(t("admin.buttons.delete_attachment", lang), callback_data="admin_delete_attachment"))
            row2.append(InlineKeyboardButton(t("admin.buttons.set_top", lang), callback_data="admin_set_top"))
        if row2:
            keyboard.append(row2)
            
        # ردیف ۳: مدیریت ساختار (سلاح‌ها و دسته‌ها) -> منتقل شده به اینجا طبق درخواست
        row3 = []
        if Permission.MANAGE_CATEGORIES in user_permissions:
             # نام دکمه‌ها از کلیدهای موجود خوانده می‌شود
             # admin.buttons.weapon_mgmt, admin.buttons.category_mgmt
             keyboard.append([
                 InlineKeyboardButton(t("admin.buttons.weapon_mgmt", lang), callback_data="admin_weapon_mgmt"),
                 InlineKeyboardButton(t("admin.buttons.category_mgmt", lang), callback_data="admin_category_mgmt")
             ])
        
        # دکمه بازگشت به منوی اصلی
        keyboard.append([
            InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        from handlers.admin.admin_states import ADMIN_MENU
        return ADMIN_MENU
