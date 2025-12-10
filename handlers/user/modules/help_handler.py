from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime

from utils.logger import log_user_action
from utils.i18n import t
from utils.language import get_user_lang
from managers.channel_manager import require_channel_membership

class HelpHandler:
    """
    Handler for help commands.
    Extracted from UserHandlers to reduce coupling.
    """
    
    def __init__(self, db):
        self.db = db
        
    @require_channel_membership
    @log_user_action("help_command")
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش راهنما (Callback)"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            t("help.text", lang),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    @require_channel_membership
    @log_user_action("help_command_msg")
    async def help_command_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش راهنما از طریق پیام"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # اضافه کردن timestamp برای جلوگیری از duplicate detection
        now = datetime.now().strftime("%H:%M:%S")
        text = f"{t('help.text', lang)} _{t('notification.updated', lang, time=now)}_"
        
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
