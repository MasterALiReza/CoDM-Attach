
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import ADMIN_MENU
from utils.logger import log_admin_action
from utils.language import get_user_lang
from utils.i18n import t
from managers.backup_scheduler import BackupScheduler

class DataManagementHandler(BaseAdminHandler):
    """
    Handler for comprehensive Data Management and Backup System.
    Replaces the old StatsBackupHandler.
    """
    
    def __init__(self, db):
        super().__init__(db)
        # We need to initialize BackupScheduler lazily or store it in context application
        self.scheduler = None # Will be retrieved from application.bot_data

    async def _get_scheduler(self, context: ContextTypes.DEFAULT_TYPE) -> BackupScheduler:
        """Helper to get scheduler instance"""
        if self.scheduler:
            return self.scheduler
        
        # Try to get from bot_data
        if 'backup_scheduler' in context.application.bot_data:
            self.scheduler = context.application.bot_data['backup_scheduler']
            return self.scheduler
            
        # If not initialized yet (shouldn't happen if main.py is correct), init temporary one
        # But really we want the one attached to the app for job queue
        scheduler = BackupScheduler(self.db)
        context.application.bot_data['backup_scheduler'] = scheduler
        self.scheduler = scheduler
        return scheduler

    async def data_management_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Main Data Management Menu"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # Get last backup info
        last_backup_time = "N/A"
        try:
            # We can use the scheduler's backup manager instance or create a temp one
            # Creating temp one is fine for reading
            from managers.backup_manager import BackupManager
            bm = BackupManager(self.db)
            last_info = bm.get_last_backup_info()
            if last_info:
                # Format: 2023-10-27T10:30:00... -> display lighter
                dt = last_info['created'].split('.')[0].replace('T', ' ')
                last_backup_time = dt
        except Exception as e:
            pass

        text = t("admin.data_mgmt.menu.title", lang) + "\n\n"
        text += t("admin.data_mgmt.menu.last_backup", lang, time=last_backup_time)

        keyboard = [
            [
                InlineKeyboardButton(t("admin.data_mgmt.btn.create_backup", lang), callback_data="admin_create_backup"),
                InlineKeyboardButton(t("admin.data_mgmt.btn.auto_backup", lang), callback_data="admin_auto_backup_menu")
            ],
            [
                InlineKeyboardButton(t("admin.health.fix.buttons.restore_backup", lang), callback_data="restore_backup")
            ],
            [
                InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")
            ]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_MENU

    async def auto_backup_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Auto Backup Settings Menu"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'

        # Get current settings
        enabled = self.db.get_setting("auto_backup_enabled", "0") == "1"
        current_interval = self.db.get_setting("auto_backup_interval", "24h")

        status_emoji = "✅" if enabled else "❌"
        status_text = t("common.enabled", lang) if enabled else t("common.disabled", lang)
        
        text = t("admin.auto_backup.menu.title", lang) + "\n\n"
        text += t("admin.auto_backup.menu.status", lang, emoji=status_emoji, status=status_text) + "\n"
        text += t("admin.auto_backup.menu.interval", lang, interval=current_interval)

        # Build interval buttons
        intervals = [("24h", "24h"), ("1w", "1w"), ("2w", "2w"), ("1m", "1m")]
        interval_row = []
        for label, val in intervals:
            # Highlight selected
            btn_text = f"• {label} •" if val == current_interval else label
            interval_row.append(InlineKeyboardButton(btn_text, callback_data=f"set_ab_interval_{val}"))

        keyboard = [
            [InlineKeyboardButton(
                t("admin.auto_backup.btn.toggle_off" if enabled else "admin.auto_backup.btn.toggle_on", lang), 
                callback_data="toggle_auto_backup"
            )],
            interval_row,
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_data_management")]
        ]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return ADMIN_MENU

    async def toggle_auto_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Toggle auto backup on/off"""
        query = update.callback_query
        await query.answer()
        
        enabled = self.db.get_setting("auto_backup_enabled", "0") == "1"
        new_state = not enabled
        current_interval = self.db.get_setting("auto_backup_interval", "24h")
        
        scheduler = await self._get_scheduler(context)
        await scheduler.update_schedule(context.application, new_state, current_interval)
        
        # Refresh menu
        await self.auto_backup_menu(update, context)

    async def set_auto_backup_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Set auto backup interval"""
        query = update.callback_query
        await query.answer()
        
        # Extract interval from callback_data: set_ab_interval_24h
        new_interval = query.data.replace("set_ab_interval_", "")
        enabled = self.db.get_setting("auto_backup_enabled", "0") == "1"
        
        scheduler = await self._get_scheduler(context)
        await scheduler.update_schedule(context.application, enabled, new_interval)
        
        # Refresh menu
        await self.auto_backup_menu(update, context)

    @log_admin_action("create_backup")
    async def create_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manual Backup Creation"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        await query.answer(t("admin.backup.processing", lang))
        await query.edit_message_text(t("admin.backup.processing", lang))
        
        bm = (await self._get_scheduler(context)).backup_manager
        backup_file = bm.create_full_backup()
        
        keyboard = [
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_data_management")]
        ]
        
        if backup_file:
            # Update last backup timestamp
            from datetime import datetime
            self.db.set_setting("last_backup_timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))

            # Send file FIRST
            with open(backup_file, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=os.path.basename(backup_file),
                    caption=t("admin.backup.file_caption", lang)
                )

            # Then delete the processing message (so we don't have duplicates or wrong order)
            try:
                await query.message.delete()
            except Exception:
                pass # If can't delete, ignore
            
            # Send Success message with the back button AS A NEW MESSAGE (so it is at bottom)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=t("admin.backup.created", lang, filename=os.path.basename(backup_file)),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                t("admin.backup.error", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return ADMIN_MENU
