from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.user.base_user_handler import BaseUserHandler
from managers.channel_manager import require_channel_membership
from utils.language import get_user_lang, set_user_lang
from utils.i18n import t
from utils.logger import get_logger
from utils.telegram_safety import safe_edit_message_text

logger = get_logger('user.settings.language', 'user.log')


class LanguageHandler(BaseUserHandler):
    """مدیریت تنظیمات زبان کاربر"""

    @require_channel_membership
    async def open_user_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی تنظیمات کاربر (ربات)"""
        query = update.callback_query
        if query:
            await query.answer()

        lang = get_user_lang(update, context, self.db) or 'fa'

        keyboard = [
            [InlineKeyboardButton(t("settings.user.language", lang), callback_data="user_settings_language")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = t("settings.user.title", lang)

        if query:
            try:
                await safe_edit_message_text(query, text, reply_markup=reply_markup)
            except Exception:
                await query.message.reply_text(text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text, reply_markup=reply_markup)

    @require_channel_membership
    async def open_language_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی انتخاب زبان"""
        query = update.callback_query
        if query:
            await query.answer()

        lang = get_user_lang(update, context, self.db) or 'fa'
        # نام زبان فعلی بر اساس i18n (نمایش در زبان کاربر)
        current_lang_name = t("lang.fa", lang) if lang == 'fa' else t("lang.en", lang)

        keyboard = [
            [
                InlineKeyboardButton(t("lang.fa", lang), callback_data="set_lang_fa"),
                InlineKeyboardButton(t("lang.en", lang), callback_data="set_lang_en"),
            ],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="user_settings_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        text = t("settings.language.current", lang, current=current_lang_name)
        text += "\n\n" + t("settings.language.choose", lang)

        try:
            await safe_edit_message_text(query, text, reply_markup=reply_markup)
        except Exception:
            await query.message.reply_text(text, reply_markup=reply_markup)

    async def set_language(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ذخیره زبان انتخابی کاربر"""
        query = update.callback_query
        await query.answer()

        data = query.data or ""
        new_lang = data.split("_")[-1] if "_" in data else None
        if new_lang not in ("fa", "en"):
            return

        ok = set_user_lang(update, context, self.db, new_lang)
        lang_name = t("lang.fa", new_lang) if new_lang == 'fa' else t("lang.en", new_lang)

        if ok:
            await query.answer(t("lang.saved", new_lang, lang_name=lang_name), show_alert=True)
            
            # شبیه‌سازی /start با ارسال keyboard (ReplyKeyboard) مانند دستور start
            try:
                # Delete inline message
                try:
                    await query.message.delete()
                except Exception:
                    pass
                
                # Import needed modules
                from telegram import ReplyKeyboardMarkup
                from utils.i18n import kb
                from managers.cms_manager import CMSManager
                
                user_id = update.effective_user.id
                
                # Build keyboard exactly like start() does
                keyboard = [
                    [kb("menu.buttons.game_settings", new_lang), kb("menu.buttons.get", new_lang)]
                ]
                
                # Check UA system
                ua_system_enabled = self.db.get_ua_setting('system_enabled')
                if ua_system_enabled == '1':
                    keyboard.append([kb("menu.buttons.ua", new_lang), kb("menu.buttons.suggested", new_lang)])
                else:
                    keyboard.append([kb("menu.buttons.suggested", new_lang)])
                
                keyboard.extend([
                    [kb("menu.buttons.season_list", new_lang), kb("menu.buttons.season_top", new_lang)],
                    [kb("menu.buttons.notify", new_lang), kb("menu.buttons.search", new_lang)],
                    [kb("menu.buttons.contact", new_lang), kb("menu.buttons.help", new_lang)]
                ])
                
                # Check CMS
                try:
                    cms_enabled = str(self.db.get_setting('cms_enabled', 'false')).lower() == 'true'
                except Exception:
                    cms_enabled = False
                if cms_enabled:
                    try:
                        cms_total = CMSManager(self.db).count_published_content(None)
                    except Exception:
                        cms_total = 0
                    if cms_total > 0:
                        keyboard.append([kb("menu.buttons.cms", new_lang)])
                
                keyboard.append([kb("menu.buttons.user_settings", new_lang)])
                
                # Check admin
                if self.db.is_admin(user_id):
                    keyboard.append([kb("menu.buttons.admin", new_lang)])
                
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                welcome_text = t("welcome", new_lang, app_name=t("app.name", new_lang))
                
                # Send message with keyboard (works from callback_query)
                await query.message.reply_text(
                    welcome_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                
            except Exception as e:
                logger.error(f"Error showing keyboard after language change: {e}")
                try:
                    await query.message.reply_text(
                        t("welcome", new_lang, app_name=t("app.name", new_lang))
                    )
                except Exception:
                    pass
        else:
            await query.answer(t("error.generic", new_lang), show_alert=True)
