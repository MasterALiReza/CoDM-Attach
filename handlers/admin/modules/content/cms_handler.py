from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from typing import Any
from handlers.admin.modules.base_handler import BaseAdminHandler
from core.security.role_manager import Permission
from handlers.admin.admin_states import (
    ADMIN_MENU,
    CMS_ADD_TYPE, CMS_ADD_TITLE, CMS_ADD_BODY, CMS_SEARCH_TEXT,
)
from managers.cms_manager import CMSManager
from utils.i18n import t
from utils.language import get_user_lang
from utils.telegram_safety import safe_edit_message_text


class CMSHandler(BaseAdminHandler):
    """هندلر مدیریت CMS سمت ادمین (CRUD ساده و انتشار/حذف)."""

    def __init__(self, db: Any) -> None:
        """سازنده هندلر.

        Args:
            db: Database adapter
        """
        super().__init__(db)
        self.cms = CMSManager(db)

    async def cms_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمایش منوی اصلی CMS برای ادمین."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'

        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.MANAGE_CMS):
            await self.send_permission_denied(update, context)
            return ADMIN_MENU

        items = self.cms.get_published_content(limit=5)
        text = t('admin.cms.menu.title', lang) + "\n\n" + t('admin.cms.menu.desc', lang) + "\n\n"
        if items:
            text += t('admin.cms.list.header', lang, n=len(items)) + "\n"
            for i in items:
                title = i.get('title') or '—'
                text += f"• {title}\n"
        else:
            text += t('admin.cms.no_data', lang) + "\n"

        keyboard = [
            [InlineKeyboardButton(t('admin.cms.buttons.add', lang), callback_data='cms_add')],
            [InlineKeyboardButton(t('admin.cms.buttons.list', lang), callback_data='cms_list')],
            [InlineKeyboardButton(t('admin.cms.buttons.search', lang), callback_data='cms_search')],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='admin_menu_return')],
        ]
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return ADMIN_MENU

    async def cms_add_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """شروع فرایند افزودن محتوا (انتخاب نوع)."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'

        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.MANAGE_CMS):
            await self.send_permission_denied(update, context)
            return ADMIN_MENU

        text = t('admin.cms.add.type_prompt', lang)
        kb = [
            [InlineKeyboardButton(t('admin.cms.type.news', lang), callback_data='cms_type_news')],
            [InlineKeyboardButton(t('admin.cms.type.tutorial', lang), callback_data='cms_type_tutorial')],
            [InlineKeyboardButton(t('admin.cms.type.event', lang), callback_data='cms_type_event')],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='admin_cms')],
        ]
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return CMS_ADD_TYPE

    async def cms_type_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """پس از انتخاب نوع، درخواست عنوان را ارسال می‌کند."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        data = query.data or ''
        ctype = data.replace('cms_type_', '')
        context.user_data['cms_type'] = ctype
        await safe_edit_message_text(query, t('admin.cms.add.title_prompt', lang), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data='admin_cms')]]))
        return CMS_ADD_TITLE

    async def cms_title_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """دریافت عنوان محتوا از پیام کاربر."""
        lang = get_user_lang(update, context, self.db) or 'fa'
        title = (update.message.text or '').strip()
        if len(title) < 3:
            await update.message.reply_text(t('admin.cms.add.title_short', lang))
            return CMS_ADD_TITLE
        context.user_data['cms_title'] = title
        await update.message.reply_text(t('admin.cms.add.body_prompt', lang))
        return CMS_ADD_BODY

    async def cms_body_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """دریافت متن محتوا و ذخیره آن در پایگاه داده."""
        lang = get_user_lang(update, context, self.db) or 'fa'
        body = (update.message.text or '').strip()
        title = context.user_data.get('cms_title')
        ctype = context.user_data.get('cms_type', 'news')
        user_id = update.effective_user.id
        cid = self.cms.create_content(ctype, title, body, author_id=user_id, tags=[])
        context.user_data.pop('cms_title', None)
        context.user_data.pop('cms_type', None)
        if cid:
            await update.message.reply_text(t('admin.cms.add.saved', lang, id=cid))
        else:
            await update.message.reply_text(t('error.generic', lang))
        return ADMIN_MENU

    async def cms_list_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمایش لیست محتوا برای مدیریت (انتشار/حذف)."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.MANAGE_CMS):
            await self.send_permission_denied(update, context)
            return ADMIN_MENU
        rows = self.cms.list_content(limit=10)
        if not rows:
            await safe_edit_message_text(query, t('admin.cms.no_data', lang), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='admin_cms')]]))
            return ADMIN_MENU
        text = t('admin.cms.list.title', lang, n=len(rows)) + "\n\n"
        kb = []
        for r in rows:
            rid = r.get('content_id') or r.get('id')
            title = r.get('title') or '—'
            text += f"• {title}\n"
            kb.append([
                InlineKeyboardButton(t('admin.cms.buttons.publish', lang), callback_data=f'cms_pub_{rid}'),
                InlineKeyboardButton(t('admin.cms.buttons.delete', lang), callback_data=f'cms_del_{rid}')
            ])
        kb.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='admin_cms')])
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
        return ADMIN_MENU

    async def cms_publish(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """انتشار یک محتوا."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        data = query.data or ''
        try:
            cid = int(data.split('_')[-1])
        except Exception:
            cid = None
        if not cid:
            await query.answer(t('error.generic', lang), show_alert=True)
            return ADMIN_MENU
        ok = self.cms.publish_content(cid)
        msg = t('admin.cms.publish.success', lang) if ok else t('error.generic', lang)
        await safe_edit_message_text(query, msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='cms_list')]]))
        return ADMIN_MENU

    async def cms_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """حذف (hard) یک محتوا."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        data = query.data or ''
        try:
            cid = int(data.split('_')[-1])
        except Exception:
            cid = None
        if not cid:
            await query.answer(t('error.generic', lang), show_alert=True)
            return ADMIN_MENU
        ok = self.cms.delete_content(cid, hard=True)
        msg = t('admin.cms.delete.success', lang) if ok else t('error.generic', lang)
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='cms_list')]]))
        return ADMIN_MENU

    async def cms_search_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """شروع جستجوی محتوا (پرامپت ورودی متن)."""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        await safe_edit_message_text(query, t('admin.cms.search.prompt', lang), reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data='admin_cms')]]), parse_mode='Markdown')
        return CMS_SEARCH_TEXT

    async def cms_search_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """دریافت متن جستجو و نمایش نتایج."""
        lang = get_user_lang(update, context, self.db) or 'fa'
        q = (update.message.text or '').strip()
        if not q:
            await update.message.reply_text(t('admin.cms.search.prompt', lang))
            return ADMIN_MENU
        rows = self.cms.search_content(q, limit=10)
        if not rows:
            await update.message.reply_text(t('admin.cms.search.no_results', lang))
            return ADMIN_MENU
        text = t('admin.cms.search.results', lang, n=len(rows)) + "\n\n"
        for r in rows:
            title = r.get('title') or '—'
            text += f"• {title}\n"
        await update.message.reply_text(text, parse_mode='Markdown')
        return ADMIN_MENU
