from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime

from managers.notification_manager import NotificationManager
from utils.logger import log_user_action
from utils.i18n import t
from utils.language import get_user_lang
from managers.channel_manager import require_channel_membership

class NotificationHandler:
    """
    Handler for managing user notification settings.
    Extracted from UserHandlers to reduce coupling.
    """
    
    def __init__(self, db, subs):
        self.db = db
        self.subs = subs
        
    async def admin_exit_and_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """خروج از پنل ادمین و نمایش تنظیمات اعلان‌ها"""
        # Flag برای جلوگیری از duplicate توسط handler عمومی
        context.user_data['_notification_shown'] = True
        # ارسال منوی تنظیمات اعلان
        await self.notification_settings(update, context)
        # خروج از admin conversation
        return ConversationHandler.END
    
    @require_channel_membership
    async def notification_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی تنظیمات اعلان‌های کاربر - یکپارچه برای message و callback"""
        user_id = update.effective_user.id
        notif_mgr = NotificationManager(self.db, self.subs)
        prefs = notif_mgr.get_user_preferences(user_id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        enabled = prefs.get('enabled', True)
        modes = prefs.get('modes', ['br', 'mp'])
        
        # اضافه کردن timestamp برای جلوگیری از duplicate detection تلگرام
        now = datetime.now().strftime("%H:%M:%S")
        
        status_txt = t('notification.enabled', lang) if enabled else t('notification.disabled', lang)
        text = t('notification.settings.title', lang) + f" {t('notification.updated', lang, time=now)}\n\n"
        text += t('notification.settings.desc', lang) + "\n\n"
        text += t('notification.status', lang, status=status_txt) + "\n\n"
        text += t('notification.modes.title', lang) + "\n"
        br_status = t('notification.enabled', lang) if 'br' in modes else t('notification.disabled', lang)
        mp_status = t('notification.enabled', lang) if 'mp' in modes else t('notification.disabled', lang)
        text += f"• {t('mode.br_short', lang)}: {br_status}\n"
        text += f"• {t('mode.mp_short', lang)}: {mp_status}\n"
        
        keyboard = []
        toggle_text = t('notification.toggle_all.disable', lang) if enabled else t('notification.toggle_all.enable', lang)
        keyboard.append([InlineKeyboardButton(toggle_text, callback_data="user_notif_toggle")])
        
        keyboard.append([
            InlineKeyboardButton(
                t('mode.br_short', lang) + (" ✅" if 'br' in modes else " ❌"),
                callback_data="user_notif_mode_br"
            ),
            InlineKeyboardButton(
                t('mode.mp_short', lang) + (" ✅" if 'mp' in modes else " ❌"),
                callback_data="user_notif_mode_mp"
            )
        ])
        
        keyboard.append([InlineKeyboardButton(t('notification.events.button', lang), callback_data="user_notif_events")])
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="main_menu")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # تشخیص نوع ورودی (message یا callback)
        if update.callback_query:
            try:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text(
                    text, reply_markup=reply_markup, parse_mode='Markdown'
                )
            except Exception:
                await update.callback_query.message.reply_text(
                    text, reply_markup=reply_markup, parse_mode='Markdown'
                )
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
    async def notification_settings_with_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Wrapper برای handler عمومی - چک می‌کنه که duplicate نباشه"""
        # اگر flag وجود داشت، skip کن (قبلاً از state handler نشون داده شده)
        if context.user_data.pop('_notification_shown', False):
            return
        return await self.notification_settings(update, context)
        
    @log_user_action("notification_toggle")
    async def notification_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن کلی اعلان‌ها"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        notif_mgr = NotificationManager(self.db, self.subs)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if notif_mgr.toggle_user_notifications(user_id):
            await query.answer(t('success.generic', lang), show_alert=False)
        else:
            await query.answer(t('error.generic', lang), show_alert=True)
        
        return await self.notification_settings(update, context)
    
    @log_user_action("notification_toggle_mode")
    async def notification_toggle_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن نوتیف برای یک مود خاص"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        mode = query.data.replace("user_notif_mode_", "")
        
        notif_mgr = NotificationManager(self.db, self.subs)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if notif_mgr.toggle_user_mode(user_id, mode):
            await query.answer(t('success.generic', lang), show_alert=False)
        else:
            await query.answer(t('error.generic', lang), show_alert=True)
        
        return await self.notification_settings(update, context)
    
    @log_user_action("notification_events_menu")
    async def notification_events_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی انتخاب رویدادها برای دریافت اعلان"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        notif_mgr = NotificationManager(self.db, self.subs)
        prefs = notif_mgr.get_user_preferences(user_id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        events = prefs.get('events', {})
        
        text = t('notification.events.title', lang) + "\n\n" + t('notification.events.desc', lang) + "\n\n"
        
        event_names = {
            "add_attachment": t('notification.event.add_attachment', lang),
            "edit_name": t('notification.event.edit_name', lang),
            "edit_image": t('notification.event.edit_image', lang),
            "edit_code": t('notification.event.edit_code', lang),
            "delete_attachment": t('notification.event.delete_attachment', lang),
            "top_set": t('notification.event.top_set', lang),
            "top_added": t('notification.event.top_added', lang),
            "top_removed": t('notification.event.top_removed', lang)
        }
        
        keyboard = []
        
        for event_key, event_name in event_names.items():
            is_enabled = events.get(event_key, True)
            status = "✅" if is_enabled else "❌"
            keyboard.append([
                InlineKeyboardButton(
                    f"{status} {event_name}",
                    callback_data=f"user_notif_event_{event_key}"
                )
            ])
            
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="user_notif_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    @log_user_action("notification_toggle_event")
    async def notification_toggle_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن یک رویداد خاص"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        event_key = query.data.replace("user_notif_event_", "")
        
        notif_mgr = NotificationManager(self.db, self.subs)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if notif_mgr.toggle_user_event(user_id, event_key):
            await query.answer(t('success.generic', lang), show_alert=False)
        else:
            await query.answer(t('error.generic', lang), show_alert=True)
            
        return await self.notification_events_menu(update, context)

    async def subscribe_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عضویت در لیست اعلان‌ها"""
        user_id = update.effective_user.id
        lang = get_user_lang(update, context, self.db) or 'fa'
        if self.subs.add(user_id):
            await update.message.reply_text(t('subscription.joined', lang))
        else:
            await update.message.reply_text(t('subscription.already_member', lang))

    async def unsubscribe_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو عضویت در لیست اعلان‌ها"""
        user_id = update.effective_user.id
        lang = get_user_lang(update, context, self.db) or 'fa'
        if self.subs.remove(user_id):
            await update.message.reply_text(t('subscription.unsubscribed', lang))
        else:
            await update.message.reply_text(t('subscription.not_member', lang))

    async def view_attachment_from_notification(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش اتچمنت از اعلان: attm__{category}__{weapon}__{code}__{mode}"""
        from utils.logger import get_logger, log_exception
        logger = get_logger('user', 'user.log')
        
        query = update.callback_query
        await query.answer()
        
        # Parse callback data با separator __
        try:
            payload = query.data.replace("attm__", "")
            parts = payload.split("__")
            
            if len(parts) != 4:
                logger.error(f"Invalid callback format: {query.data}")
                lang = get_user_lang(update, context, self.db) or 'fa'
                await query.answer(t('error.generic', lang), show_alert=True)
                return
            
            category, weapon, code, mode = parts
            logger.info(f"Parsed notification callback - Category: {category}, Weapon: {weapon}, Code: {code}, Mode: {mode}")
            
        except Exception as e:
            logger.error(f"Error parsing notification callback: {e}")
            log_exception(logger, e, "context")
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t('error.generic', lang), show_alert=True)
            return
        
        # دریافت اتچمنت از دیتابیس
        attachments = self.db.get_all_attachments(category, weapon, mode=mode)
        selected = next((att for att in attachments if att.get('code') == code), None)
        
        if not selected:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t('attachment.not_found', lang), show_alert=True)
            return
        
        # ارسال اتچمنت
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_short = t(f"mode.{mode}_btn", lang)
        cat_name = t(f"category.{category}", lang)
        caption = f"**{selected['name']}**\n"
        caption += f"{t('weapon.label', lang)}: {weapon} ({cat_name})\n"
        caption += f"{t('mode.label', lang)}: {mode_short}\n"
        caption += f"{t('attachment.code', lang)}: `{selected['code']}`\n\n{t('attachment.tap_to_copy', lang)}"
        # آمار بازخورد + ثبت بازدید
        att_id = selected.get('id')
        stats = self.db.get_attachment_stats(att_id, period='all') if att_id else {}
        like_count = stats.get('like_count', 0)
        dislike_count = stats.get('dislike_count', 0)
        if att_id:
            self.db.track_attachment_view(query.from_user.id, att_id)
        feedback_kb = None
        if att_id:
            feedback_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                    InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
                ],
                [InlineKeyboardButton(t('attachment.copy_code', lang), callback_data=f"att_copy_{att_id}")],
                [InlineKeyboardButton(t('attachment.feedback', lang), callback_data=f"att_fb_{att_id}")]
            ])
        
        try:
            if selected.get('image'):
                await query.message.reply_photo(
                    photo=selected['image'], 
                    caption=caption, 
                    parse_mode='Markdown',
                    reply_markup=feedback_kb
                )
            else:
                await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=feedback_kb)
            
            await query.answer(t('success.generic', lang))
        except Exception as e:
            logger.error(f"Error sending attachment from notification: {e}")
            log_exception(logger, e, "context")
            await query.message.reply_text(caption, parse_mode='Markdown')
            await query.answer(t('success.generic', lang))
