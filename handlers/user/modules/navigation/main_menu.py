"""
مدیریت منوی اصلی و navigation
⚠️ این کد عیناً از user_handlers.py خط 91-141 کپی شده
"""

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from config.config import GAME_MODES
from managers.channel_manager import require_channel_membership
from utils.analytics_pg import AnalyticsPostgres as Analytics
from handlers.user.base_user_handler import BaseUserHandler
from utils.logger import get_logger, log_exception
from utils.language import get_user_lang
from utils.i18n import t, kb
from managers.cms_manager import CMSManager

logger = get_logger('user', 'user.log')


class MainMenuHandler(BaseUserHandler):
    """مدیریت منوی اصلی ربات"""
    
    @require_channel_membership
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دستور شروع و نمایش منوی اصلی"""
        user_id = update.effective_user.id
        try:
            if context.args and len(context.args) > 0:
                context.user_data['start_param'] = context.args[0]
        except Exception:
            pass

        # Deep-link actions
        param = context.user_data.get('start_param')
        if param and update.message:
            # /start att-{id}-{mode}
            if param.startswith("att-"):
                try:
                    parts = param.split("-")
                    att_id = int(parts[1]) if len(parts) > 1 else None
                    mode = parts[2] if len(parts) > 2 else 'br'
                except Exception:
                    att_id, mode = None, 'br'
                if att_id:
                    att = self.db.get_attachment_by_id(att_id)
                    if att:
                        lang = get_user_lang(update, context, self.db) or 'fa'
                        mode_name = t(f"mode.{mode}_btn", lang)
                        weapon = att.get('weapon') or att.get('weapon_name') or ''
                        caption = f"**{att.get('name','')}**\n{t('attachment.code', lang)}: `{att.get('code','')}`\n{weapon} | {mode_name}"
                        # دکمه‌های بازخورد
                        feedback_kb = None
                        a_id = att.get('id')
                        if a_id:
                            try:
                                stats = self.db.get_attachment_stats(a_id, period='all') or {}
                                like_count = stats.get('like_count', 0)
                                dislike_count = stats.get('dislike_count', 0)
                            except Exception:
                                like_count = dislike_count = 0
                            feedback_kb = InlineKeyboardMarkup([
                                [InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{a_id}"), InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{a_id}")],
                                [InlineKeyboardButton(t('attachment.copy_code', lang), callback_data=f"att_copy_{a_id}")],
                                [InlineKeyboardButton(t('attachment.feedback', lang), callback_data=f"att_fb_{a_id}")]
                            ])
                        try:
                            if att.get('image'):
                                await update.message.reply_photo(photo=att['image'], caption=caption, parse_mode='Markdown', reply_markup=feedback_kb)
                            else:
                                await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=feedback_kb)
                                return
                            return
                        except Exception:
                            await update.message.reply_text(caption, parse_mode='Markdown', reply_markup=feedback_kb)
                            return
            # /start allw-{category}__{weapon}__{mode}
            if param.startswith("allw-"):
                try:
                    payload = param.replace("allw-", "")
                    category, weapon, mode = payload.split("__", 3)
                except Exception:
                    category = weapon = None
                    mode = 'br'
                if category and weapon:
                    items = self.db.get_all_attachments(category, weapon, mode=mode) or []
                    lang = get_user_lang(update, context, self.db) or 'fa'
                    mode_name = t(f"mode.{mode}_btn", lang)
                    if not items:
                        await update.message.reply_text(t('attachment.none', lang))
                        return
                    header = t('attachment.all.title', lang, weapon=weapon, mode=mode_name)
                    lines = [header]
                    for i, att in enumerate(items[:20], start=1):
                        lines.append(f"{i}. {att.get('name','?')} — `{att.get('code','')}`")
                    await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
                    return

        # Track user info in database (NEW - for analytics)
        self._track_user_info(update)

        # Analytics: ثبت ورود کاربر
        try:
            analytics = Analytics()
            analytics.track_user_start(user_id)
        except Exception as e:
            logger.error(f"[Analytics] Error tracking user start: {e}")
            log_exception(logger, e, "context")

        # ثبت خودکار کاربر به عنوان مشترک برای دریافت نوتیفیکیشن‌ها
        try:
            self.subs.add(user_id)
        except Exception as e:
            logger.warning(f"Error registering user {user_id} for notifications: {e}")

        lang = get_user_lang(update, context, self.db) or 'fa'

        keyboard = [
            [kb("menu.buttons.game_settings", lang), kb("menu.buttons.get", lang)]
        ]
        
        # ردیف 2: بسته به فعال بودن سیستم اتچمنت کاربران
        ua_system_enabled = self.db.get_ua_setting('system_enabled')
        if ua_system_enabled == '1':
            keyboard.append([kb("menu.buttons.ua", lang), kb("menu.buttons.suggested", lang)])
        else:
            keyboard.append([kb("menu.buttons.suggested", lang)])
        
        keyboard.extend([
            [kb("menu.buttons.season_list", lang), kb("menu.buttons.season_top", lang)],
            [kb("menu.buttons.notify", lang), kb("menu.buttons.search", lang)],
            [kb("menu.buttons.contact", lang), kb("menu.buttons.help", lang)]
        ])

        # ردیف CMS (نمایش مشروط به فعال بودن و داشتن محتوا)
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
                keyboard.append([kb("menu.buttons.cms", lang)])

        keyboard.append([kb("menu.buttons.user_settings", lang)])

        # اگر کاربر ادمین است، دکمه پنل ادمین را اضافه کن (بررسی از دیتابیس RBAC)
        if self.db.is_admin(user_id):
            keyboard.append([kb("menu.buttons.admin", lang)])

        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        welcome_text = t("welcome", lang, app_name=t("app.name", lang))
        await update.message.reply_text(
            welcome_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    async def back_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بازگشت به منوی اصلی از طریق پیام"""
        return await self.start(update, context)

    async def main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بازگشت به منوی اصلی (Inline)"""
        query = update.callback_query
        await query.answer()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        keyboard = [
            [InlineKeyboardButton(kb("menu.buttons.get", lang), callback_data="select_mode_first")],
            [InlineKeyboardButton(kb("menu.buttons.season_top", lang), callback_data="season_top")],
            [InlineKeyboardButton(kb("menu.buttons.season_list", lang), callback_data="season_top_list")],
            [InlineKeyboardButton(kb("menu.buttons.suggested", lang), callback_data="suggested_attachments")]
        ]
        # نمایش مشروط CMS: فقط اگر فعال باشد و محتوای منتشرشده وجود داشته باشد
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
                keyboard.append([InlineKeyboardButton(kb("menu.buttons.cms", lang), callback_data="cms")])
        
        # چک کردن فعال بودن سیستم اتچمنت کاربران
        ua_system_enabled = self.db.get_ua_setting('system_enabled')
        if ua_system_enabled == '1':
            keyboard.append([InlineKeyboardButton(kb("menu.buttons.ua", lang), callback_data="ua_menu")])
        
        keyboard.extend([
            [InlineKeyboardButton(kb("menu.buttons.search", lang), callback_data="search")],
            [InlineKeyboardButton(kb("menu.buttons.help", lang), callback_data="help")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Try to edit the message text; if current message is media (photo), fall back
        try:
            await query.edit_message_text(
                t("welcome", lang, app_name=t("app.name", lang)),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except Exception:
            # When the current message is a photo (no text), Telegram raises
            # "BadRequest: There is no text in the message to edit". Fallback to delete+reply.
            try:
                await query.message.delete()
            except Exception:
                pass
            await query.message.reply_text(
                t("welcome", lang, app_name=t("app.name", lang)),
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        # CRITICAL: باید ConversationHandler.END برگردونه تا جستجو لغو بشه
        return ConversationHandler.END
