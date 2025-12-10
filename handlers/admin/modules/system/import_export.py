"""
ماژول Import/Export داده
مسئول: ورود و خروج داده از دیتابیس
"""

import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import IMPORT_FILE, IMPORT_MODE, EXPORT_TYPE
from utils.logger import log_admin_action, log_exception, get_logger
from utils.telegram_safety import safe_edit_message_text

logger = get_logger('import_export', 'admin.log')


class ImportExportHandler(BaseAdminHandler):
    """Handler برای Import/Export داده"""
    
    @log_admin_action("import_start")
    async def import_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع import دیتا"""
        query = update.callback_query
        await query.answer()
        
        # بررسی دسترسی
        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        
        if Permission.IMPORT_EXPORT not in user_permissions:
            await query.answer("❌ شما دسترسی Import/Export ندارید.", show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU
        
        keyboard = [
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_data_management")]
        ]
        
        await safe_edit_message_text(
            query,
            "📥 **Import دیتا**\n\n"
            "فایل JSON یا ZIP حاوی دیتای جدید را ارسال کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return IMPORT_FILE
    
    @log_admin_action("import_file_received")
    async def import_file_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت فایل import"""
        if not update.message.document:
            await update.message.reply_text("❌ لطفاً یک فایل ارسال کنید.")
            return await self.admin_menu_return(update, context)
        
        # بررسی نوع فایل
        file_name = update.message.document.file_name
        if not file_name.endswith(('.json', '.zip')):
            await update.message.reply_text("❌ فقط فایل‌های JSON یا ZIP پشتیبانی می‌شوند.")
            return await self.admin_menu_return(update, context)
        
        await update.message.reply_text("⏳ در حال پردازش فایل...")
        
        file = await update.message.document.get_file()
        temp_file = f"temp_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}{os.path.splitext(file_name)[1]}"
        await file.download_to_drive(temp_file)
        
        try:
            from managers.backup_manager import BackupManager
            backup_mgr = BackupManager(self.db)
            
            # اگر فایل ZIP است، restore کن
            if temp_file.endswith('.zip'):
                result = backup_mgr.restore_from_backup(temp_file)
                if result:
                    await update.message.reply_text(
                        "✅ بازیابی از backup با موفقیت انجام شد.\n"
                        "🔄 لطفاً ربات را ری‌استارت کنید."
                    )
                else:
                    await update.message.reply_text("❌ خطا در بازیابی از backup.")
            # اگر فایل JSON است، import کن
            else:
                keyboard = [
                    [InlineKeyboardButton("➕ افزودن به دیتای موجود", callback_data="import_merge")],
                    [InlineKeyboardButton("🔄 جایگزینی کامل", callback_data="import_replace")],
                    [InlineKeyboardButton("❌ لغو", callback_data="admin_cancel")]
                ]
                context.user_data['import_temp_file'] = temp_file
                await update.message.reply_text(
                    "⚠️ نحوه import را انتخاب کنید:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                return IMPORT_MODE
                
        except Exception as e:
            logger.error(f"Import error: {e}")
            log_exception(logger, e, "context")
            await update.message.reply_text(f"❌ خطا در import: {str(e)}")
        
        # حذف فایل موقت
        if os.path.exists(temp_file) and 'import_temp_file' not in context.user_data:
            os.remove(temp_file)
        
        return await self.admin_menu_return(update, context)
    
    @log_admin_action("import_mode_selected")
    async def import_mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب نحوه import"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "admin_cancel":
            temp_file = context.user_data.pop('import_temp_file', None)
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            return await self.admin_menu_return(update, context)
        
        temp_file = context.user_data.get('import_temp_file')
        if not temp_file or not os.path.exists(temp_file):
            await safe_edit_message_text(query, "❌ فایل import یافت نشد.")
            return await self.admin_menu_return(update, context)
        
        merge = (query.data == "import_merge")
        
        try:
            from managers.backup_manager import BackupManager
            backup_mgr = BackupManager(self.db)
            
            await safe_edit_message_text(query, "⏳ در حال import دیتا...")
            
            result = backup_mgr.import_from_json(temp_file, merge=merge)
            
            if result:
                mode = "افزودن" if merge else "جایگزینی"
                await safe_edit_message_text(query, f"✅ دیتا با موفقیت به صورت {mode} import شد.")
            else:
                await safe_edit_message_text(query, "❌ خطا در import دیتا.")
                
        except Exception as e:
            logger.error(f"Import mode error: {e}")
            log_exception(logger, e, "context")
            await safe_edit_message_text(query, f"❌ خطا: {str(e)}")
        
        # حذف فایل موقت
        context.user_data.pop('import_temp_file', None)
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        return await self.admin_menu_return(update, context)
    
    @log_admin_action("export_start")
    async def export_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع export دیتا با گزینه‌های مختلف"""
        query = update.callback_query
        await query.answer()
        
        # بررسی دسترسی
        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        
        if Permission.IMPORT_EXPORT not in user_permissions:
            await query.answer("❌ شما دسترسی Import/Export ندارید.", show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU
        
        keyboard = [
            [InlineKeyboardButton("📦 Export کامل (JSON)", callback_data="export_json")],
            [InlineKeyboardButton("📊 Export به CSV", callback_data="export_csv")],
            [InlineKeyboardButton("🗄️ Backup کامل (ZIP)", callback_data="export_backup")],
            [InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_data_management")]
        ]
        
        await safe_edit_message_text(
            query,
            "📤 **Export دیتا**\n\n"
            "نوع export را انتخاب کنید:\n\n"
            "• **JSON**: قابل import مجدد در ربات\n"
            "• **CSV**: برای Excel و تحلیل‌های آماری\n"
            "• **ZIP**: بکاپ کامل همه فایل‌ها",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return EXPORT_TYPE
    
    @log_admin_action("export_type_selected")
    async def export_type_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب نوع export"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        await safe_edit_message_text(query, "⏳ در حال آماده‌سازی export...")
        
        try:
            from managers.backup_manager import BackupManager
            backup_mgr = BackupManager(self.db)
            
            export_file = None
            caption = ""
            
            if query.data == "export_json":
                export_file = backup_mgr.export_to_json()
                caption = "📦 Export دیتابیس (JSON)\n\n✅ قابل import مجدد در ربات"
                
            elif query.data == "export_csv":
                export_dir = backup_mgr.export_to_csv()
                if export_dir:
                    # Create ZIP from CSV files
                    import zipfile
                    export_file = export_dir + ".zip"
                    with zipfile.ZipFile(export_file, 'w') as zf:
                        for root, dirs, files in os.walk(export_dir):
                            for file in files:
                                file_path = os.path.join(root, file)
                                zf.write(file_path, os.path.basename(file_path))
                    # Clean up CSV directory
                    import shutil
                    shutil.rmtree(export_dir)
                    caption = "📊 Export دیتابیس (CSV)\n\n✅ قابل استفاده در Excel"
                
            elif query.data == "export_backup":
                export_file = backup_mgr.create_full_backup()
                caption = "🗄️ Backup کامل دیتابیس\n\n✅ شامل همه فایل‌ها و تنظیمات"
            
            if export_file and os.path.exists(export_file):
                with open(export_file, 'rb') as f:
                    await query.message.reply_document(
                        document=f,
                        filename=os.path.basename(export_file),
                        caption=caption
                    )
                
                # Get file size
                file_size = os.path.getsize(export_file) / 1024  # KB
                if file_size > 1024:
                    file_size = f"{file_size/1024:.2f} MB"
                else:
                    file_size = f"{file_size:.2f} KB"
                
                await safe_edit_message_text(
                    query,
                    f"✅ Export با موفقیت انجام شد.\n"
                    f"📁 حجم فایل: {file_size}"
                )
                
                # Clean up after sending
                if os.path.exists(export_file):
                    os.remove(export_file)
            else:
                await safe_edit_message_text(query, "❌ خطا در Export دیتا.")
                
        except Exception as e:
            logger.error(f"Export error: {e}")
            log_exception(logger, e, "context")
            await safe_edit_message_text(query, f"❌ خطا در Export: {str(e)}")
        
        return await self.admin_menu_return(update, context)
