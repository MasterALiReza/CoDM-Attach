"""
ماژول پشتیبان‌گیری دیتابیس
مسئول: فقط مدیریت بکاپ (بدون بخش آمار ربات)
"""

import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import ADMIN_MENU
from utils.logger import log_admin_action
from utils.language import get_user_lang
from utils.i18n import t

class StatsBackupHandler(BaseAdminHandler):
    """Handler برای پشتیبان‌گیری دیتابیس"""
    
    @log_admin_action("create_backup")
    async def create_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ایجاد بکاپ از دیتابیس"""
        query = update.callback_query
        await query.answer()
        
        # بررسی دسترسی
        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        if Permission.BACKUP_DATA not in user_permissions:
            await query.answer(t("admin.backup.no_permission", lang), show_alert=True)
            return ADMIN_MENU
        
        backup_file = self.db.backup_database()
        
        keyboard = [
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_data_management")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if backup_file:
            await query.edit_message_text(
                t("admin.backup.created", lang, filename=os.path.basename(backup_file)),
                reply_markup=reply_markup
            )
            
            # ارسال فایل بکاپ
            with open(backup_file, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=os.path.basename(backup_file),
                    caption=t("admin.backup.file_caption", lang)
                )
        else:
            await query.edit_message_text(
                t("admin.backup.error", lang),
                reply_markup=reply_markup
            )
        
        return ADMIN_MENU

