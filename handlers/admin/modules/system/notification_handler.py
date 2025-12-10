"""
ماژول مدیریت اعلان‌ها (Notifications)
مسئول: ارسال پیام به کاربران و مدیریت تنظیمات اعلان
"""

import asyncio
from datetime import datetime, timezone, timedelta
import json
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import Forbidden, BadRequest
from config.config import NOTIFICATION_SETTINGS
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import NOTIF_COMPOSE, NOTIF_CONFIRM, ADMIN_MENU
from utils.subscribers_pg import SubscribersPostgres as Subscribers
from utils.logger import log_admin_action, get_logger
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text

logger = get_logger('notification', 'admin.log')


class NotificationHandler(BaseAdminHandler):
    """Handler برای مدیریت اعلان‌ها و پیام‌های عمومی"""
    
    @log_admin_action("notify_start")
    async def notify_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ورود به بخش اعلان‌ها: منوی اصلی اعلان با دو گزینه"""
        query = update.callback_query
        await query.answer()
        
        # بررسی دسترسی
        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        
        # نمایش منوی اصلی اعلان
        return await self.notify_home_menu(update, context)

    @log_admin_action("notify_home")
    async def notify_home_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی اصلی اعلان‌ها: ارسال اعلان | پیام‌های زمان‌بندی‌شده | بازگشت"""
        query = update.callback_query
        await query.answer()

        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        lang = get_user_lang(update, context, self.db) or 'fa'

        if Permission.SEND_NOTIFICATIONS not in user_permissions and not self.role_manager.is_super_admin(query.from_user.id):
            await query.answer(t("admin.notify.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        # محتوای منوی اعلان‌ها
        text = t("admin.notify.home.text", lang)

        keyboard = [[InlineKeyboardButton(t("admin.notify.buttons.compose", lang), callback_data="notify_compose")]]
        if (Permission.MANAGE_SCHEDULED_NOTIFICATIONS in user_permissions) or self.role_manager.is_super_admin(query.from_user.id):
            keyboard.append([InlineKeyboardButton(t("admin.notify.buttons.scheduled", lang), callback_data="admin_sched_notifications")])
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")])

        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard))

        from handlers.admin.admin_states import ADMIN_MENU
        return ADMIN_MENU

    @log_admin_action("schedule_edit_open")
    async def schedule_edit_open(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش جزئیات یک زمان‌بندی و گزینه ویرایش متن"""
        query = update.callback_query
        await query.answer()

        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        if Permission.MANAGE_SCHEDULED_NOTIFICATIONS not in user_permissions and not self.role_manager.is_super_admin(query.from_user.id):
            await query.answer(t("common.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        try:
            sid = int(query.data.replace("sched_edit_", ""))
        except Exception:
            return await self.schedules_menu(update, context)

        row = self.db.get_scheduled_notification_by_id(sid)
        if not row:
            await query.answer(t("common.not_found", lang), show_alert=True)
            return await self.schedules_menu(update, context)

        def status_text(enabled: bool) -> str:
            return t("common.status.enabled", lang) if enabled else t("common.status.disabled", lang)

        # Local datetime formatter (Tehran, no microseconds)
        def _fmt_dt_local(dt):
            try:
                if not dt:
                    return "—"
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                iran_tz = timezone(timedelta(hours=3, minutes=30))
                local = dt.astimezone(iran_tz)
                return local.strftime('%Y-%m-%d • %H:%M (UTC+03:30)')
            except Exception:
                return "—"

        text = (
            t("admin.notify.schedule.edit.title", lang) + "\n\n" +
            t("admin.notify.schedule.edit.header", lang, id=row['id'], status=status_text(row['enabled']), hours=row['interval_hours']) + "\n" +
            t("admin.notify.schedule.edit.next", lang, next=_fmt_dt_local(row.get('next_run_at')))
        )

        if row.get('message_type') == 'text':
            preview = (row.get('message_text') or '').replace('\n', ' ')[:120]
            if preview:
                text += "\n" + t("admin.notify.schedule.edit.text_preview", lang, preview=preview)
            m_kb = [[InlineKeyboardButton(t("admin.notify.buttons.edit_text", lang), callback_data=f"sched_edit_text_{sid}")]]
        else:
            cap = (row.get('message_text') or '').replace('\n', ' ')[:120]
            if cap:
                text += "\n" + t("admin.notify.schedule.edit.photo_caption_preview", lang, cap=cap)
            else:
                text += "\n" + t("admin.notify.schedule.edit.photo_no_caption", lang)
            m_kb = [[InlineKeyboardButton(t("admin.notify.buttons.edit_caption", lang), callback_data=f"sched_edit_text_{sid}")]]

        m_kb.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_sched_notifications")])
        await safe_edit_message_text(query, text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(m_kb))

        from handlers.admin.admin_states import ADMIN_MENU
        return ADMIN_MENU

    @log_admin_action("schedule_edit_text_start")
    async def schedule_edit_text_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع ویرایش متن/کپشن زمان‌بندی"""
        query = update.callback_query
        await query.answer()

        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        if Permission.MANAGE_SCHEDULED_NOTIFICATIONS not in user_permissions and not self.role_manager.is_super_admin(query.from_user.id):
            await query.answer(t("common.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        try:
            sid = int(query.data.replace("sched_edit_text_", ""))
        except Exception:
            return await self.schedules_menu(update, context)

        context.user_data['sched_edit_id'] = sid
        msg = t("admin.notify.schedule.edit_text.prompt", lang)
        kb = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_sched_notifications")]]
        await safe_edit_message_text(query, msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

        from handlers.admin.admin_states import SCHED_EDIT_TEXT
        return SCHED_EDIT_TEXT

    @log_admin_action("schedule_edit_text_received")
    async def schedule_edit_text_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت متن جدید و ذخیره در زمان‌بندی"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not update.message or not update.message.text:
            await update.message.reply_text(t("admin.notify.schedule.edit_text.only_text", lang))
            from handlers.admin.admin_states import SCHED_EDIT_TEXT
            return SCHED_EDIT_TEXT

        sid = context.user_data.get('sched_edit_id')
        if not sid:
            await update.message.reply_text(t("common.invalid_id", lang))
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        new_text = update.message.text
        ok = self.db.update_scheduled_notification(
            schedule_id=int(sid),
            message_type='text',
            message_text=new_text,
            photo_file_id=None,
        )

        context.user_data.pop('sched_edit_id', None)

        if ok:
            kb = [[InlineKeyboardButton(t("admin.notify.buttons.back_to_schedules", lang), callback_data="admin_sched_notifications")]]
            await update.message.reply_text(t("admin.notify.schedule.edit_text.success", lang), reply_markup=InlineKeyboardMarkup(kb))
        else:
            kb = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_sched_notifications")]]
            await update.message.reply_text(t("admin.notify.schedule.edit_text.error", lang), reply_markup=InlineKeyboardMarkup(kb))

        from handlers.admin.admin_states import ADMIN_MENU
        return ADMIN_MENU

    @log_admin_action("notify_compose_start")
    async def notify_compose_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع فرآیند نوشتن اعلان (نمایش راهنما و ورود به حالت نوشتن)"""
        query = update.callback_query
        await query.answer()

        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        if Permission.SEND_NOTIFICATIONS not in user_permissions and not self.role_manager.is_super_admin(query.from_user.id):
            await query.answer(t("admin.notify.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        # تعداد مخاطبین
        subs = Subscribers()
        count = subs.count()

        if count == 0:
            await safe_edit_message_text(
                query,
                t("admin.notify.no_subscribers", lang),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="notify_home")]])
            )
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        text = t("admin.notify.compose.help", lang, count=count)

        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="notify_home")]]
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

        from handlers.admin.admin_states import NOTIF_COMPOSE
        return NOTIF_COMPOSE
    
    @log_admin_action("schedules_menu")
    async def schedules_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لیست زمان‌بندی‌های اعلان با امکان فعال/غیرفعال و حذف"""
        query = update.callback_query
        await query.answer()

        # Permission check
        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        if Permission.MANAGE_SCHEDULED_NOTIFICATIONS not in user_permissions and not self.role_manager.is_super_admin(query.from_user.id):
            await query.answer(t("admin.notify.schedule.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        items = self.db.list_scheduled_notifications() or []

        def fmt_bool(b):
            return "✅" if b else "❌"

        def fmt_dt(dt):
            """نمایش تاریخ به شکل خوانا بدون میکروثانیه و با منطقه زمانی تهران"""
            try:
                if not dt:
                    return "—"
                # اطمینان از timezone-aware بودن
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                iran_tz = timezone(timedelta(hours=3, minutes=30))
                local = dt.astimezone(iran_tz)
                return local.strftime('%Y-%m-%d • %H:%M (UTC+03:30)')
            except Exception:
                return "—"

        text = t("admin.notify.schedules.title", lang) + "\n\n"
        if not items:
            text += t("admin.notify.schedules.empty", lang)
        else:
            for it in items[:20]:
                sid = it['id']
                status_text = t("common.status.enabled", lang) if it['enabled'] else t("common.status.disabled", lang)
                interval = it.get('interval_hours') or 0
                text += (
                    t("admin.notify.schedules.item.header", lang, sid=sid, status=status_text, hours=interval) + "\n" +
                    t("admin.notify.schedules.item.next", lang, next=fmt_dt(it.get('next_run_at'))) + "\n"
                )
                # نمایش نوع پیام
                mtype = it.get('message_type', 'text')
                if mtype == 'text':
                    preview = (it.get('message_text') or '')
                    if preview:
                        preview = preview.replace('\n', ' ')[:60]
                        text += t("admin.notify.schedules.item.text", lang, preview=preview) + "\n"
                else:
                    cap = (it.get('message_text') or '').replace('\n', ' ')[:60]
                    if cap:
                        text += t("admin.notify.schedules.item.photo_caption", lang, cap=cap) + "\n"
                    else:
                        text += t("admin.notify.schedules.item.photo", lang) + "\n"
                text += "\n"

        # Build keyboard
        keyboard = []
        for it in items[:10]:
            sid = it['id']
            en_btn = InlineKeyboardButton(
                (t("admin.notify.buttons.disable", lang) if it['enabled'] else t("admin.notify.buttons.enable", lang)),
                callback_data=f"sched_toggle_{sid}"
            )
            del_btn = InlineKeyboardButton(t("common.delete", lang), callback_data=f"sched_delete_{sid}")
            edit_btn = InlineKeyboardButton(t("common.edit", lang), callback_data=f"sched_edit_{sid}")
            keyboard.append([en_btn, del_btn])
            keyboard.append([edit_btn])

        keyboard.append([InlineKeyboardButton(t("menu.buttons.refresh", lang), callback_data="admin_sched_notifications")])
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="notify_home")])

        try:
            await safe_edit_message_text(
                query,
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except BadRequest as e:
            # اگر هیچ تغییری نسبت به متن فعلی نکرده بودیم
            if 'Message is not modified' in str(e):
                await query.answer(t("admin.notify.schedules.nothing_to_update", lang))
            else:
                raise

        from handlers.admin.admin_states import ADMIN_MENU
        return ADMIN_MENU

    @log_admin_action("schedule_toggle")
    async def schedule_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        if Permission.MANAGE_SCHEDULED_NOTIFICATIONS not in user_permissions and not self.role_manager.is_super_admin(query.from_user.id):
            await query.answer(t("common.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        sid = int(query.data.replace("sched_toggle_", ""))
        row = self.db.get_scheduled_notification_by_id(sid)
        if not row:
            await query.answer(t("common.not_found", lang), show_alert=True)
            return await self.schedules_menu(update, context)
        self.db.set_schedule_enabled(sid, not row['enabled'])
        return await self.schedules_menu(update, context)

    @log_admin_action("schedule_delete")
    async def schedule_delete(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        if Permission.MANAGE_SCHEDULED_NOTIFICATIONS not in user_permissions and not self.role_manager.is_super_admin(query.from_user.id):
            await query.answer(t("common.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU

        sid = int(query.data.replace("sched_delete_", ""))
        self.db.delete_scheduled_notification(sid)
        await query.answer(t("common.deleted", lang))
        return await self.schedules_menu(update, context)
        
    
    @log_admin_action("notify_compose_received")
    async def notify_compose_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت متن یا عکس اعلان و نمایش پیش‌نمایش"""
        # اگر در حالت ویرایش قالب هستیم
        if context.user_data.get('tmpl_key'):
            lang = get_user_lang(update, context, self.db) or 'fa'
            if not update.message.text:
                await update.message.reply_text(t("admin.notify.templates.only_text", lang))
                return NOTIF_COMPOSE
            
            key = context.user_data['tmpl_key']
            NOTIFICATION_SETTINGS['templates'][key] = update.message.text
            self._persist_notification_settings()
            context.user_data.pop('tmpl_key', None)
            await update.message.reply_text(t("admin.notify.templates.saved", lang))
            return await self.notify_home_menu(update, context)
        
        subs = Subscribers()
        count = subs.count()
        
        # پاکسازی داده‌های قبلی
        context.user_data['notif_type'] = None
        context.user_data['notif_text'] = None
        context.user_data['notif_photo'] = None
        
        # بررسی نوع پیام
        lang = get_user_lang(update, context, self.db) or 'fa'
        if update.message.photo:
            context.user_data['notif_type'] = 'photo'
            context.user_data['notif_photo'] = update.message.photo[-1].file_id
            context.user_data['notif_text'] = update.message.caption or ''
            
            preview_caption = (context.user_data['notif_text'] or '') + "\n\n" + t("admin.notify.preview.footer", lang, count=count)
            keyboard = [
                [InlineKeyboardButton(t("admin.notify.buttons.confirm_send", lang), callback_data="notify_confirm")],
                [InlineKeyboardButton(t("admin.notify.buttons.schedule_next", lang), callback_data="notify_schedule")],
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="notify_home")]
            ]
            
            try:
                await update.message.reply_photo(
                    photo=context.user_data['notif_photo'],
                    caption=preview_caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                # اگر Markdown غلط بود، بدون parse_mode ارسال کن
                await update.message.reply_photo(
                    photo=context.user_data['notif_photo'],
                    caption=preview_caption + "\n\n" + t("admin.notify.markdown_error", lang),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            return NOTIF_CONFIRM
        
        elif update.message.text:
            context.user_data['notif_type'] = 'text'
            context.user_data['notif_text'] = update.message.text
        
            preview_text = update.message.text + "\n\n" + t("admin.notify.preview.footer", lang, count=count)
            keyboard = [
                [InlineKeyboardButton(t("admin.notify.buttons.confirm_send", lang), callback_data="notify_confirm")],
                [InlineKeyboardButton(t("admin.notify.buttons.schedule_next", lang), callback_data="notify_schedule")],
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="notify_home")]
            ]
            
            try:
                await update.message.reply_text(
                    preview_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                # اگر Markdown غلط بود، بدون parse_mode ارسال کن
                await update.message.reply_text(
                    preview_text + "\n\n" + t("admin.notify.markdown_error", lang),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            return NOTIF_CONFIRM
        
        await update.message.reply_text(t("admin.notify.compose.only_text_or_photo", lang))
        return NOTIF_COMPOSE
    
    @log_admin_action("notify_confirm")
    async def notify_confirm_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ارسال پیام به همه کاربران ثبت‌شده با گزارش پیشرفت"""
        query = update.callback_query
        await query.answer()
        
        if query.data != 'notify_confirm':
            return await self.notify_home_menu(update, context)
        
        subs = Subscribers()
        ids = subs.all()
        
        # یکتا سازی و حذف مقادیر نامعتبر
        ids = [int(i) for i in set(ids) if isinstance(i, int) or (isinstance(i, str) and i.isdigit())]
        
        total = len(ids)
        sent = 0
        failed = 0
        removed = 0
        
        notif_type = context.user_data.get('notif_type')
        text = context.user_data.get('notif_text') or ''
        photo = context.user_data.get('notif_photo')
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        # پیام وضعیت
        await query.message.edit_text(t("admin.notify.send.start", lang))
        initial_bar = "▱" * 10
        status_msg = await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=t("admin.notify.send.progress", lang, bar=initial_bar + " 0%", percent=0, current=0, total=total, sent=0, failed=0)
        )
        
        for idx, uid in enumerate(ids, 1):
            try:
                if notif_type == 'photo' and photo:
                    try:
                        await context.bot.send_photo(
                            chat_id=uid,
                            photo=photo,
                            caption=text or None,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        # اگر Markdown خطا داد، بدون parse_mode ارسال کن
                        await context.bot.send_photo(
                            chat_id=uid,
                            photo=photo,
                            caption=text or None
                        )
                else:
                    try:
                        await context.bot.send_message(
                            chat_id=uid,
                            text=text,
                            parse_mode='Markdown'
                        )
                    except Exception:
                        # اگر Markdown خطا داد، بدون parse_mode ارسال کن
                        await context.bot.send_message(
                            chat_id=uid,
                            text=text
                        )
                sent += 1
            except Forbidden:
                # کاربر ربات را بلاک کرده؛ از لیست حذف شود
                if subs.remove(uid):
                    removed += 1
                failed += 1
            except Exception:
                failed += 1
            
            # به‌روزرسانی وضعیت هر 10 ارسال یا در پایان
            if idx % 10 == 0 or idx == total:
                try:
                    progress = int((idx / total) * 10)
                    bar = "▰" * progress + "▱" * (10 - progress)
                    percent = int((idx / total) * 100)
                    
                    bar_str = ("▰" * progress) + ("▱" * (10 - progress))
                    await status_msg.edit_text(
                        t("admin.notify.send.progress", lang, bar=f"{bar_str} {percent}%", percent=percent, current=sent + failed, total=total, sent=sent, failed=failed)
                    )
                except Exception:
                    pass
            
            # محدودیت نرخ
            await asyncio.sleep(0.03)
        
        # نتیجه نهایی
        success_rate = int((sent / total) * 100) if total > 0 else 0
        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="notify_home")]]
        try:
            await status_msg.edit_text(
                t("admin.notify.send.summary", lang, total=total, sent=sent, success_rate=success_rate, failed=failed, removed=removed, avg=0.03),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            pass
        
        # پاکسازی داده‌های موقت
        for k in ['notif_type', 'notif_text', 'notif_photo']:
            context.user_data.pop(k, None)
        
        return await self.notify_home_menu(update, context)
    
    @log_admin_action("notify_schedule_menu")
    async def notify_schedule_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش گزینه‌های زمان‌بندی برای پیام آماده شده"""
        query = update.callback_query
        await query.answer()

        # اطمینان از اینکه پیام آماده وجود دارد
        notif_type = context.user_data.get('notif_type')
        notif_text = context.user_data.get('notif_text')
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not notif_type or (notif_type == 'text' and not notif_text):
            await query.answer(t("admin.notify.compose.only_text_or_photo", lang), show_alert=True)
            return await self.admin_menu_return(update, context)

        text = (
            t("admin.notify.schedule.menu.title", lang) + "\n\n" +
            t("admin.notify.schedule.menu.desc", lang) + "\n" +
            f"• {t('admin.notify.schedule.menu.6h', lang)}\n" +
            f"• {t('admin.notify.schedule.menu.12h', lang)}\n" +
            f"• {t('admin.notify.schedule.menu.24h', lang)}\n" +
            f"• {t('admin.notify.schedule.menu.48h', lang)}\n"
        )

        keyboard = [
            [InlineKeyboardButton(t("admin.notify.schedule.menu.6h", lang), callback_data="notif_sched_6h"), InlineKeyboardButton(t("admin.notify.schedule.menu.12h", lang), callback_data="notif_sched_12h")],
            [InlineKeyboardButton(t("admin.notify.schedule.menu.24h", lang), callback_data="notif_sched_24h")],
            [InlineKeyboardButton(t("admin.notify.schedule.menu.48h", lang), callback_data="notif_sched_48h")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="notify_home")]
        ]

        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        from handlers.admin.admin_states import NOTIF_CONFIRM
        return NOTIF_CONFIRM

    @log_admin_action("notify_schedule_preset")
    async def notify_schedule_preset_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ایجاد رکورد زمان‌بندی با یکی از پریست‌ها"""
        query = update.callback_query
        await query.answer()

        data = query.data
        hours_map = {
            'notif_sched_6h': 6,
            'notif_sched_12h': 12,
            'notif_sched_24h': 24,
            'notif_sched_48h': 48,
        }
        if data not in hours_map:
            return await self.notify_schedule_menu(update, context)

        interval_hours = hours_map[data]

        notif_type = context.user_data.get('notif_type')
        notif_text = context.user_data.get('notif_text') or ''
        notif_photo = context.user_data.get('notif_photo')

        # ایجاد زمان اجرای بعدی
        now_utc = datetime.now(timezone.utc)
        next_run_at = now_utc + timedelta(hours=interval_hours)

        try:
            new_id = self.db.create_scheduled_notification(
                message_type='photo' if (notif_type == 'photo' and notif_photo) else 'text',
                message_text=notif_text if notif_type == 'text' else notif_text,
                photo_file_id=notif_photo if notif_type == 'photo' else None,
                parse_mode='Markdown',
                interval_hours=interval_hours,
                next_run_at=next_run_at,
                enabled=True,
                created_by=query.from_user.id,
            )
        except Exception as e:
            logger.error(f"Failed to create schedule: {e}")
            new_id = None

        if new_id:
            try:
                await query.answer(t("admin.notify.schedule.saved", lang), show_alert=False)
            except Exception:
                pass
            return await self.notify_home_menu(update, context)
        else:
            await safe_edit_message_text(
                query,
                t("admin.notify.schedule.error", lang),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="notify_home")]])
            )
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU
    
    @log_admin_action("notify_settings_menu")
    async def notify_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی تنظیمات اعلان‌ها"""
        query = update.callback_query
        await query.answer()
        
        # بررسی دسترسی
        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        if Permission.MANAGE_NOTIFICATION_SETTINGS not in user_permissions:
            await query.answer(t("admin.notify.schedule.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU
        
        # دریافت تنظیمات فعلی
        enabled = NOTIFICATION_SETTINGS.get('enabled', True)
        auto_notify = NOTIFICATION_SETTINGS.get('auto_notify', True)
        
        text = (
            t("admin.notify.settings.title", lang) + "\n\n" +
            t("admin.notify.settings.status", lang, status=t("common.status.enabled", lang) if enabled else t("common.status.disabled", lang)) + "\n" +
            t("admin.notify.settings.auto", lang, status=t("common.status.enabled", lang) if auto_notify else t("common.status.disabled", lang)) + "\n\n" +
            t("admin.notify.settings.templates", lang)
        )
        
        keyboard = [
            [InlineKeyboardButton(
                t("admin.notify.settings.toggle.disable", lang) if enabled else t("admin.notify.settings.toggle.enable", lang),
                callback_data="notif_toggle"
            )],
            [InlineKeyboardButton(
                t("admin.notify.settings.auto.toggle.off", lang) if auto_notify else t("admin.notify.settings.auto.toggle.on", lang),
                callback_data="notif_auto_toggle"
            )],
            [InlineKeyboardButton(t("admin.notify.settings.edit_templates", lang), callback_data="notif_templates")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")]
        ]
        
        await safe_edit_message_text(
            query,
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        from handlers.admin.admin_states import ADMIN_MENU
        return ADMIN_MENU
    
    @log_admin_action("notify_toggle")
    async def notify_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن سیستم اعلان"""
        query = update.callback_query
        await query.answer()
        
        NOTIFICATION_SETTINGS['enabled'] = not NOTIFICATION_SETTINGS.get('enabled', True)
        self._persist_notification_settings()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        status_msg = t("admin.notify.settings.toggled.enabled", lang) if NOTIFICATION_SETTINGS['enabled'] else t("admin.notify.settings.toggled.disabled", lang)
        await query.answer(status_msg, show_alert=True)
        
        return await self.notify_settings_menu(update, context)
    
    @log_admin_action("notify_auto_toggle")
    async def notify_auto_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن اعلان خودکار"""
        query = update.callback_query
        await query.answer()
        
        NOTIFICATION_SETTINGS['auto_notify'] = not NOTIFICATION_SETTINGS.get('auto_notify', True)
        self._persist_notification_settings()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        status_msg = t("admin.notify.settings.auto.toggled.enabled", lang) if NOTIFICATION_SETTINGS['auto_notify'] else t("admin.notify.settings.auto.toggled.disabled", lang)
        await query.answer(status_msg, show_alert=True)
        
        return await self.notify_settings_menu(update, context)
    
    @log_admin_action("notif_toggle_global")
    async def notif_toggle_global(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن کل سیستم اعلان‌ها"""
        query = update.callback_query
        await query.answer()
        
        NOTIFICATION_SETTINGS['enabled'] = not NOTIFICATION_SETTINGS.get('enabled', True)
        self._persist_notification_settings()
        
        return await self.notify_settings_menu(update, context)
    
    @log_admin_action("notif_toggle_event")
    async def notif_toggle_event(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن اعلان برای یک رویداد خاص"""
        query = update.callback_query
        await query.answer()
        
        ev = query.data.replace("notifset_toggle_event_", "")
        cur = NOTIFICATION_SETTINGS.get('events', {}).get(ev, False)
        NOTIFICATION_SETTINGS['events'][ev] = not cur
        
        self._persist_notification_settings()
        return await self.notify_settings_menu(update, context)
    
    @log_admin_action("template_list_menu")
    async def template_list_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی انتخاب رویدادها برای ارسال اعلان"""
        query = update.callback_query
        await query.answer()
        
        # دریافت تنظیمات فعلی
        events = NOTIFICATION_SETTINGS.get('events', {})
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = t("notification.events.title", lang) + "\n\n" + t("notification.events.desc", lang) + "\n\n"
        
        # نام رویدادها از locale
        event_names = {
            "add_attachment": t("notification.event.add_attachment", lang),
            "edit_name": t("notification.event.edit_name", lang),
            "edit_image": t("notification.event.edit_image", lang),
            "edit_code": t("notification.event.edit_code", lang),
            "delete_attachment": t("notification.event.delete_attachment", lang),
            "top_set": t("notification.event.top_set", lang),
            "top_added": t("notification.event.top_added", lang),
            "top_removed": t("notification.event.top_removed", lang)
        }
        
        keyboard = []
        
        # دکمه‌های رویدادها - 2 ستونی
        row = []
        for event_key, event_name in event_names.items():
            is_enabled = events.get(event_key, False)
            status = "✅" if is_enabled else "❌"
            btn = InlineKeyboardButton(
                f"{status} {event_name}",
                callback_data=f"notif_event_{event_key}"
            )
            row.append(btn)
            
            if len(row) == 1:  # یک ستونی برای خوانایی بهتر
                keyboard.append(row)
                row = []
        
        # اگر ردیف ناقص بود، اضافه کن
        if row:
            keyboard.append(row)
        
        # دکمه بازگشت
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_notify_settings")])
        
        await safe_edit_message_text(
            query,
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        from handlers.admin.admin_states import ADMIN_MENU
        return ADMIN_MENU
    
    @log_admin_action("notif_event_toggle")
    async def notif_event_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن یک رویداد خاص"""
        query = update.callback_query
        await query.answer()
        
        event = query.data.replace("notif_event_", "")
        
        # Toggle event
        if 'events' not in NOTIFICATION_SETTINGS:
            NOTIFICATION_SETTINGS['events'] = {}
        
        current = NOTIFICATION_SETTINGS['events'].get(event, False)
        NOTIFICATION_SETTINGS['events'][event] = not current
        
        # ذخیره تنظیمات
        self._persist_notification_settings()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        status = t("common.status.enabled", lang) if NOTIFICATION_SETTINGS['events'][event] else t("common.status.disabled", lang)
        await query.answer(t("admin.notify.events.toggled", lang, status=status), show_alert=False)
        
        # بازگشت به منوی رویدادها
        return await self.template_list_menu(update, context)
    
    async def template_edit_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع ویرایش قالب پیام"""
        query = update.callback_query
        await query.answer()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        key = query.data.replace("tmpl_edit_", "")
        context.user_data['tmpl_key'] = key
        
        cur = NOTIFICATION_SETTINGS.get('templates', {}).get(key, '')
        placeholders = "{category} {category_name} {weapon} {code} {name} {old_name} {new_name} {old_code} {new_code}"
        text = (
            t("admin.notify.templates.edit.title", lang, key=key) + "\n\n" +
            t("admin.notify.templates.edit.prompt", lang, placeholders=placeholders)
        )
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_notify_settings")]]
        await safe_edit_message_text(
            query,
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return NOTIF_COMPOSE
    
    def _persist_notification_settings(self) -> bool:
        """ذخیره NOTIFICATION_SETTINGS در config.py"""
        try:
            import os
            config_path = os.path.join('config', 'config.py')
            
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # استفاده از json برای حفظ کاراکترهای فارسی
            rendered = json.dumps(NOTIFICATION_SETTINGS, ensure_ascii=False, indent=4)
            # تبدیل JSON syntax به Python syntax
            rendered = rendered.replace('true', 'True').replace('false', 'False').replace('null', 'None')
            
            # پیدا کردن NOTIFICATION_SETTINGS با balanced braces
            start_match = re.search(r'NOTIFICATION_SETTINGS\s*=\s*\{', content)
            if not start_match:
                logger.error("Could not find NOTIFICATION_SETTINGS in config.py")
                return False
            
            start_idx = start_match.start()
            brace_count = 0
            end_idx = start_match.end() - 1  # شروع از {
            
            # پیدا کردن } متناظر
            for i in range(start_match.end() - 1, len(content)):
                if content[i] == '{':
                    brace_count += 1
                elif content[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            # جایگزینی
            content_new = content[:start_idx] + f"NOTIFICATION_SETTINGS = {rendered}" + content[end_idx:]
            
            if content_new != content:
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(content_new)
                logger.info("Notification settings persisted to config.py")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"خطا در ذخیره تنظیمات اعلان‌ها: {e}")
            return False
