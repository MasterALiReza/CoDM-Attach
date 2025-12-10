from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from typing import Any, Tuple, List
import math
from managers.channel_manager import require_channel_membership
from utils.logger import log_user_action
from utils.language import get_user_lang
from utils.i18n import t
from handlers.user.base_user_handler import BaseUserHandler
from managers.cms_manager import CMSManager
from config.config import ITEMS_PER_PAGE
from utils.telegram_safety import safe_edit_message_text


class CMSUserHandler(BaseUserHandler):
    """هندلر نمایش محتوای CMS برای کاربران."""

    def __init__(self, db: Any) -> None:
        """سازنده هندلر.

        Args:
            db: Database adapter
        """
        super().__init__(db)
        self.cms = CMSManager(db)

    @require_channel_membership
    @log_user_action("cms_home")
    async def cms_home(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """نمایش منوی CMS (انتخاب نوع محتوا) از طریق Callback."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        try:
            cms_enabled = str(self.db.get_setting('cms_enabled', 'false')).lower() == 'true'
        except Exception:
            cms_enabled = False
        total = 0
        try:
            total = self.cms.count_published_content(None)
        except Exception:
            total = 0
        if (not cms_enabled) or total <= 0:
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='main_menu')]]
            text = t('cms.disabled', lang)
            try:
                await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            except Exception:
                await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return

        keyboard = [
            [
                InlineKeyboardButton(t('cms.types.news', lang), callback_data='cms_type_news'),
                InlineKeyboardButton(t('cms.types.tutorial', lang), callback_data='cms_type_tutorial')
            ],
            [InlineKeyboardButton(t('cms.types.event', lang), callback_data='cms_type_event')],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='main_menu')]
        ]

        text = t('cms.choose_type', lang)
        try:
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception:
            await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    @require_channel_membership
    @log_user_action("cms_home_msg")
    async def cms_home_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """نمایش منوی CMS (انتخاب نوع محتوا) از طریق پیام."""
        lang = get_user_lang(update, context, self.db) or 'fa'
        try:
            cms_enabled = str(self.db.get_setting('cms_enabled', 'false')).lower() == 'true'
        except Exception:
            cms_enabled = False
        total = 0
        try:
            total = self.cms.count_published_content(None)
        except Exception:
            total = 0
        if (not cms_enabled) or total <= 0:
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='main_menu')]]
            await update.message.reply_text(t('cms.disabled', lang), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return
        keyboard = [
            [
                InlineKeyboardButton(t('cms.types.news', lang), callback_data='cms_type_news'),
                InlineKeyboardButton(t('cms.types.tutorial', lang), callback_data='cms_type_tutorial')
            ],
            [InlineKeyboardButton(t('cms.types.event', lang), callback_data='cms_type_event')],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='main_menu')]
        ]
        await update.message.reply_text(t('cms.choose_type', lang), reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    @require_channel_membership
    @log_user_action("cms_type_selected")
    async def cms_type_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """نمایش لیست محتوای منتشرشده برای نوع انتخابی."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        try:
            cms_enabled = str(self.db.get_setting('cms_enabled', 'false')).lower() == 'true'
        except Exception:
            cms_enabled = False
        total = 0
        try:
            total = self.cms.count_published_content(None)
        except Exception:
            total = 0
        if (not cms_enabled) or total <= 0:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='main_menu')]])
            try:
                await safe_edit_message_text(query, t('cms.disabled', lang), reply_markup=kb, parse_mode='Markdown')
            except Exception:
                await query.message.reply_text(t('cms.disabled', lang), reply_markup=kb, parse_mode='Markdown')
            return
        ctype = query.data.replace('cms_type_', '')
        context.user_data['cms_current_type'] = ctype
        # صفحه اول
        page = 1
        text, markup = self._cms_build_page(ctype, page, lang)
        context.user_data['cms_page'] = page
        await safe_edit_message_text(query, text, reply_markup=markup)

    def _cms_build_page(self, ctype: str, page: int, lang: str) -> Tuple[str, InlineKeyboardMarkup]:
        """ساخت صفحه فهرست محتوای CMS با صفحه‌بندی ساده.

        - از ITEMS_PER_PAGE برای اندازه صفحه استفاده می‌کند.
        - برای تشخیص وجود صفحه بعدی، یک آیتم بیشتر می‌گیرد.
        """
        # محاسبه pagination کل و clamp صفحه
        total = self.cms.count_published_content(ctype)
        total_pages = max(1, math.ceil(total / ITEMS_PER_PAGE))
        page = max(1, min(page, total_pages))
        # محاسبه offset
        offset = (page - 1) * ITEMS_PER_PAGE
        # گرفتن یک آیتم بیشتر برای تشخیص next
        rows = self.cms.get_published_content(content_type=ctype, limit=ITEMS_PER_PAGE + 1, offset=offset)
        has_next = len(rows) > ITEMS_PER_PAGE
        page_items = rows[:ITEMS_PER_PAGE]

        if not page_items:
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='cms')]]
            return t('cms.no_data', lang), InlineKeyboardMarkup(keyboard)

        # ساخت کیبورد آیتم‌ها با تاریخ انتشار
        keyboard: List[List[InlineKeyboardButton]] = []
        for it in page_items:
            cid = it.get('content_id') or it.get('id')
            title = (it.get('title') or '—').strip()
            pub = it.get('published_at')
            # نمایش تاریخ به صورت YYYY-MM-DD اگر موجود باشد
            date_txt = ''
            try:
                if pub:
                    # pub ممکن است string یا datetime باشد
                    dt_str = str(pub)[:10]
                    date_txt = f" ({dt_str})"
            except Exception:
                date_txt = ''
            keyboard.append([InlineKeyboardButton(f"{title[:52]}{date_txt}", callback_data=f'cms_view_{cid}')])

        # ناوبری صفحات
        nav_row: List[InlineKeyboardButton] = []
        if page > 1:
            nav_row.append(InlineKeyboardButton(t('nav.prev', lang), callback_data=f'cmslist_page_{page-1}'))
        # دکمه میانی نمایش صفحه/کل
        nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data='noop'))
        if has_next:
            nav_row.append(InlineKeyboardButton(t('nav.next', lang), callback_data=f'cmslist_page_{page+1}'))
        if nav_row:
            keyboard.append(nav_row)

        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='cms')])
        # عنوان + نمایش شماره صفحه/کل
        text = t('cms.list.title', lang, count=total) + "\n" + t('pagination.page_of', lang, page=page, total=total_pages)
        return text, InlineKeyboardMarkup(keyboard)

    @require_channel_membership
    @log_user_action("cms_list_page_nav")
    async def cms_list_page_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """مدیریت ناوبری بین صفحات فهرست CMS."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        try:
            cms_enabled = str(self.db.get_setting('cms_enabled', 'false')).lower() == 'true'
        except Exception:
            cms_enabled = False
        if not cms_enabled:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='main_menu')]])
            await safe_edit_message_text(query, t('cms.disabled', lang), reply_markup=kb)
            return
        ctype = context.user_data.get('cms_current_type') or 'news'
        # استخراج شماره صفحه
        try:
            page = int(query.data.replace('cmslist_page_', ''))
        except Exception:
            page = 1
        text, markup = self._cms_build_page(ctype, page, lang)
        context.user_data['cms_page'] = page
        await safe_edit_message_text(query, text, reply_markup=markup)

    @require_channel_membership
    @log_user_action("cms_view")
    async def cms_view(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """نمایش جزئیات یک محتوای CMS منتشرشده."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        try:
            cms_enabled = str(self.db.get_setting('cms_enabled', 'false')).lower() == 'true'
        except Exception:
            cms_enabled = False
        if not cms_enabled:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='main_menu')]])
            try:
                await safe_edit_message_text(query, t('cms.disabled', lang), reply_markup=kb, parse_mode='Markdown')
            except Exception:
                await query.message.reply_text(t('cms.disabled', lang), reply_markup=kb, parse_mode='Markdown')
            return
        try:
            cid = int(query.data.replace('cms_view_', ''))
        except Exception:
            await query.answer(t('error.generic', lang), show_alert=True)
            return
        item = self.cms.get_content(cid)
        if not item or item.get('status') != 'published':
            await query.answer(t('cms.no_data', lang), show_alert=True)
            return
        title = item.get('title') or ''
        body = item.get('body') or ''
        pub = item.get('published_at')
        date_txt = ''
        try:
            if pub:
                date_txt = f" ({str(pub)[:10]})"
        except Exception:
            date_txt = ''
        text = f"**{title}{date_txt}**\n\n{body[:3500]}"
        ctype = context.user_data.get('cms_current_type')
        back_cb = f'cms_type_{ctype}' if ctype else 'cms'
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=back_cb)]])
        try:
            await safe_edit_message_text(query, text, reply_markup=kb, parse_mode='Markdown')
        except Exception:
            await query.message.reply_text(text, reply_markup=kb, parse_mode='Markdown')
