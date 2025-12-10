"""
مدیریت نمایش اتچمنت‌های برتر
⚠️ این کد عیناً از user_handlers.py خط 598-833 کپی شده
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.config import GAME_MODES
from managers.channel_manager import require_channel_membership
from utils.logger import log_user_action, get_logger
from utils.language import get_user_lang
from utils.i18n import t
from handlers.user.base_user_handler import BaseUserHandler
from utils.telegram_safety import safe_edit_message_text


logger = get_logger('user', 'user.log')


class TopAttachmentsHandler(BaseUserHandler):
    """مدیریت نمایش اتچمنت‌های برتر"""
    
    @require_channel_membership
    @log_user_action("show_top_attachments")

    async def show_top_attachments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش 5 اتچمنت برتر با پشتیبانی از mode"""
        query = update.callback_query
        await query.answer()
        
        category = context.user_data.get('current_category')
        weapon_name = context.user_data.get('current_weapon')
        mode = context.user_data.get('current_mode', 'br')
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        top_attachments = self.db.get_top_attachments(category, weapon_name, mode=mode)
        
        mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}"
        
        if not top_attachments:
            await safe_edit_message_text(
                query,
                t('attachment.none', lang),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"mode_{mode}_{weapon_name}")
                ]])
            )
            return
        
        # ارسال اتچمنت‌ها با عکس
        media_group = []
        for i, att in enumerate(top_attachments, 1):
            caption = f"**#{i} - {att['name']}**\n{t('attachment.code', lang)}: `{att['code']}`"
            # آمار بازخورد + ثبت بازدید
            att_id = att.get('id')
            stats = self.db.get_attachment_stats(att_id, period='all') if att_id else {}
            like_count = stats.get('like_count', 0)
            dislike_count = stats.get('dislike_count', 0)
            if att_id:
                self.db.track_attachment_view(query.from_user.id, att_id)
            # کیبورد بازخورد
            keyboard = None
            if att_id:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                        InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
                    ],
                    [InlineKeyboardButton(t('attachment.copy_code', lang), callback_data=f"att_copy_{att_id}")],
                    [InlineKeyboardButton(t('attachment.feedback', lang), callback_data=f"att_fb_{att_id}")]
                ])
            
            if att.get('image'):
                # اگر عکس وجود داشت
                try:
                    await query.message.reply_photo(
                        photo=att['image'],
                        caption=caption,
                        parse_mode='Markdown',
                        reply_markup=keyboard
                    )
                except Exception as e:
                    logger.warning(f"Error sending top attachment image (id={att_id}): {e}")
                    # اگر عکس معتبر نبود فقط متن
                    await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=keyboard)
            else:
                await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=keyboard)
        
        # دکمه بازگشت
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"mode_{mode}_{weapon_name}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.reply_text(
            t('attachment.top.title', lang, weapon=weapon_name, mode=mode_name),
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    @require_channel_membership
    @log_user_action("show_top_attachments_msg")

    async def show_top_attachments_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش اتچمنت‌های برتر از طریق پیام (کیبورد پایین) با پشتیبانی از mode"""
        from datetime import datetime
        
        category = context.user_data.get('current_category')
        weapon_name = context.user_data.get('current_weapon')
        mode = context.user_data.get('current_mode', 'br')
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not category or not weapon_name:
            await update.message.reply_text(t('weapon.select_first', lang))
            return
        
        top_attachments = self.db.get_top_attachments(category, weapon_name, mode=mode)
        if not top_attachments:
            mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}"
            await update.message.reply_text(t("attachment.none", lang))
            return
        
        # اضافه کردن پیام بروزرسانی در اولین عکس
        now = datetime.now().strftime("%H:%M:%S")
        
        for i, att in enumerate(top_attachments, 1):
            caption = f"**#{i} - {att['name']}** _{t('notification.updated', lang, time=now)}_\n{t('attachment.code', lang)}: `{att['code']}`\n\n{t('attachment.tap_to_copy', lang)}"
            # آمار بازخورد + ثبت بازدید
            att_id = att.get('id')
            stats = self.db.get_attachment_stats(att_id, period='all') if att_id else {}
            like_count = stats.get('like_count', 0)
            dislike_count = stats.get('dislike_count', 0)
            if att_id:
                user = update.effective_user
                self.db.track_attachment_view(user.id if user else None, att_id)
            keyboard = None
            if att_id:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                        InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
                    ],
                    [InlineKeyboardButton(t("attachment.copy_code", lang), callback_data=f"att_copy_{att_id}")],
                    [InlineKeyboardButton(t("attachment.feedback", lang), callback_data=f"att_fb_{att_id}")]
                ])
            try:
                if att.get('image'):
                    await update.message.reply_photo(photo=att['image'], caption=caption, parse_mode='Markdown', reply_markup=keyboard)
                else:
                    await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=keyboard)
            except Exception:
                await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=keyboard)
            # فقط برای اولین عکس timestamp اضافه می‌شه
            break
        
        # بقیه عکس‌ها بدون timestamp
        for i, att in enumerate(top_attachments[1:], 2):
            caption = f"**#{i} - {att['name']}**\n{t('attachment.code', lang)}: `{att['code']}`\n\n{t('attachment.tap_to_copy', lang)}"
            # آمار بازخورد + ثبت بازدید
            att_id = att.get('id')
            stats = self.db.get_attachment_stats(att_id, period='all') if att_id else {}
            like_count = stats.get('like_count', 0)
            dislike_count = stats.get('dislike_count', 0)
            if att_id:
                user = update.effective_user
                self.db.track_attachment_view(user.id if user else None, att_id)
            keyboard = None
            if att_id:
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                        InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
                    ],
                    [InlineKeyboardButton(t('attachment.copy_code', lang), callback_data=f"att_copy_{att_id}")],
                    [InlineKeyboardButton(t('attachment.feedback', lang), callback_data=f"att_fb_{att_id}")]
                ])
            try:
                if att.get('image'):
                    await update.message.reply_photo(photo=att['image'], caption=caption, parse_mode='Markdown', reply_markup=keyboard)
                else:
                    await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=keyboard)
            except Exception:
                await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=keyboard)
