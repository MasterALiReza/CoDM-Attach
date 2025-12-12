"""
ماژول مدیریت تیکت‌های پشتیبانی
مسئول: مدیریت درخواست‌های پشتیبانی کاربران
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from html import escape as html_escape
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import ADMIN_MENU, TICKET_SEARCH, TICKET_REPLY
from utils.logger import log_admin_action, get_logger
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text

logger = get_logger('ticket_handler', 'admin.log')


class TicketHandler(BaseAdminHandler):
    """Handler برای مدیریت تیکت‌های پشتیبانی"""
    
    async def _notify_user_status_change(self, context, ticket, new_status):
        """ارسال notification به کاربر در صورت تغییر وضعیت"""
        try:
            # زبان کاربر را از DB بگیر
            try:
                lang = self.db.get_user_language(ticket['user_id']) or 'fa'
            except Exception:
                lang = 'fa'
            # متن وضعیت با i18n
            status_text = t(f"ticket.status.{new_status}", lang)
            # پیام دوزبانه
            message = (
                t("user.tickets.update.title", lang, id=ticket['id']) + "\n\n"
                + t("user.tickets.status.changed", lang, status=status_text) + "\n"
                + t("user.tickets.subject", lang, subject=html_escape(ticket['subject']))
            )
            
            await context.bot.send_message(
                chat_id=ticket['user_id'],
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to notify user about status change: {e}")
    
    async def _notify_user_priority_change(self, context, ticket, new_priority):
        """ارسال notification به کاربر در صورت تغییر اولویت"""
        try:
            # زبان کاربر را از DB بگیر
            try:
                lang = self.db.get_user_language(ticket['user_id']) or 'fa'
            except Exception:
                lang = 'fa'
            # متن اولویت با i18n
            priority_text = t(f"ticket.priority.{new_priority}", lang)
            # پیام دوزبانه
            message = (
                t("user.tickets.update.title", lang, id=ticket['id']) + "\n\n"
                + t("user.tickets.priority.changed", lang, priority=priority_text) + "\n"
                + t("user.tickets.subject", lang, subject=html_escape(ticket['subject']))
            )
            
            await context.bot.send_message(
                chat_id=ticket['user_id'],
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to notify user about priority change: {e}")
    
    async def _notify_user_assignment(self, context, ticket, admin_id):
        """ارسال notification به کاربر در صورت واگذاری"""
        try:
            # زبان کاربر را از DB بگیر
            try:
                lang = self.db.get_user_language(ticket['user_id']) or 'fa'
            except Exception:
                lang = 'fa'
            message = (
                t("user.tickets.update.title", lang, id=ticket['id']) + "\n\n"
                + t("user.tickets.assignment", lang) + "\n"
                + t("user.tickets.subject", lang, subject=html_escape(ticket['subject']))
            )
            
            await context.bot.send_message(
                chat_id=ticket['user_id'],
                text=message,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Failed to notify user about assignment: {e}")
    
    async def _show_ticket_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE, query, ticket_id: int):
        """نمایش جزئیات تیکت - helper function"""
        ticket = self.db.get_ticket(ticket_id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if not ticket:
            await safe_edit_message_text(query, t("admin.tickets.not_found", lang))
            return False
        
        # Escape برای HTML
        subject = html_escape(ticket['subject'])
        description = html_escape(ticket['description'][:200])
        
        # Priority / Status localized
        priority_key = ticket.get('priority', 'medium')
        priority_text = t(f"ticket.priority.{priority_key}", lang)
        status_key = ticket.get('status', 'open')
        status_text = t(f"ticket.status.{status_key}", lang)
        
        text = t("admin.tickets.detail.title", lang, id=ticket_id) + "\n\n"
        text += t("admin.tickets.detail.user", lang, user_id=ticket['user_id']) + "\n"
        text += t("admin.tickets.detail.category", lang, category=ticket['category']) + "\n"
        text += t("admin.tickets.detail.subject", lang, subject=subject) + "\n"
        text += t("admin.tickets.detail.priority", lang, priority=priority_text) + "\n"
        text += t("admin.tickets.detail.status", lang, status=status_text) + "\n"
        text += t("admin.tickets.detail.date", lang, date=ticket['created_at'][:16]) + "\n"
        
        # نمایش ادمین مسئول اگر وجود دارد
        if ticket.get('assigned_to'):
            text += t("admin.tickets.detail.assigned", lang, admin_id=ticket['assigned_to']) + "\n"
        
        text += "\n" + t("admin.tickets.detail.description_header", lang) + "\n" + description + "\n"
        
        # نمایش تعداد پاسخ‌ها
        replies = self.db.get_ticket_replies(ticket_id)
        if replies:
            text += "\n" + t("admin.tickets.detail.replies_header", lang, count=len(replies))
            # نمایش آخرین پاسخ
            last_reply = replies[-1]
            reply_type = t("admin.tickets.detail.reply.by_admin", lang) if last_reply.get('is_admin') else t("admin.tickets.detail.reply.by_user", lang)
            reply_time = last_reply.get('created_at', '')[:16]
            text += f"\n├─ {t('admin.tickets.detail.replies.last', lang, by=reply_type, time=reply_time)}"
        
        keyboard = [
            [InlineKeyboardButton(t("admin.tickets.buttons.reply", lang), callback_data=f"adm_reply_{ticket_id}"),
             InlineKeyboardButton(t("admin.tickets.buttons.attach", lang), callback_data=f"adm_attach_{ticket_id}")],
            [InlineKeyboardButton(t("admin.tickets.buttons.change_status", lang), callback_data=f"adm_status_{ticket_id}"),
             InlineKeyboardButton(t("admin.tickets.buttons.change_priority", lang), callback_data=f"adm_priority_{ticket_id}")],
            [InlineKeyboardButton(t("admin.tickets.buttons.assign", lang), callback_data=f"adm_assign_{ticket_id}"),
             InlineKeyboardButton(t("admin.tickets.buttons.close", lang), callback_data=f"adm_close_{ticket_id}")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")]
        ]
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return True
    
    @log_admin_action("admin_tickets_menu")
    async def admin_tickets_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی مدیریت تیکت‌ها"""
        query = update.callback_query
        await query.answer()
        
        # بررسی دسترسی
        from core.security.role_manager import Permission
        user_id = update.effective_user.id
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if not self.role_manager.has_permission(user_id, Permission.MANAGE_TICKETS):
            await safe_edit_message_text(query, t("common.no_permission", lang))
            return ADMIN_MENU
        
        # دریافت آمار
        stats = self.db.get_ticket_stats()
        
        text = t("admin.tickets.menu.title", lang) + "\n\n"
        text += t("admin.tickets.menu.stats.header", lang) + "\n"
        text += t("admin.tickets.menu.stats.open", lang, n=stats.get('open', 0)) + "\n"
        text += t("admin.tickets.menu.stats.in_progress", lang, n=stats.get('in_progress', 0)) + "\n"
        text += t("admin.tickets.menu.stats.waiting_user", lang, n=stats.get('waiting_user', 0)) + "\n"
        text += t("admin.tickets.menu.stats.resolved", lang, n=stats.get('resolved', 0)) + "\n"
        text += t("admin.tickets.menu.stats.closed", lang, n=stats.get('closed', 0)) + "\n\n"
        text += t("admin.tickets.menu.stats.total", lang, n=stats.get('total', 0))
        
        keyboard = [
            [InlineKeyboardButton(t("admin.tickets.buttons.new", lang), callback_data="adm_tickets_new"),
             InlineKeyboardButton(t("admin.tickets.buttons.in_progress", lang), callback_data="adm_tickets_progress")],
            [InlineKeyboardButton(t("admin.tickets.buttons.waiting_user", lang), callback_data="adm_tickets_waiting"),
             InlineKeyboardButton(t("admin.tickets.buttons.resolved", lang), callback_data="adm_tickets_resolved")],
            [InlineKeyboardButton(t("admin.tickets.buttons.all", lang), callback_data="adm_tickets_all"),
             InlineKeyboardButton(t("admin.tickets.buttons.search", lang), callback_data="adm_tickets_search")],
            [InlineKeyboardButton(t("admin.tickets.buttons.filter_category", lang), callback_data="adm_tickets_filter_category"),
             InlineKeyboardButton(t("admin.tickets.buttons.mine", lang), callback_data="adm_tickets_mine")],
            [InlineKeyboardButton("💬 تماس مستقیم", callback_data="adm_direct_contact")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_back")]
        ]
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return ADMIN_MENU
    
    def _paginate_tickets(self, tickets: list, page: int = 1, per_page: int = 8):
        """Helper برای pagination تیکت‌ها"""
        total = len(tickets)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        page = max(1, min(page, total_pages))
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_tickets = tickets[start_idx:end_idx]
        
        return {
            'tickets': page_tickets,
            'page': page,
            'total_pages': total_pages,
            'total': total,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'start_idx': start_idx,
            'end_idx': min(end_idx, total)
        }
    
    @log_admin_action("admin_tickets_list")
    async def admin_tickets_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیست تیکت‌ها"""
        query = update.callback_query
        await query.answer()
        
        # نقشه وضعیت‌ها
        status_map = {
            'adm_tickets_new': 'open',
            'adm_tickets_progress': 'in_progress',
            'adm_tickets_waiting': 'waiting_user',
            'adm_tickets_resolved': 'resolved',
            'adm_tickets_all': None
        }
        
        status = status_map.get(query.data)
        
        # ذخیره status در context برای pagination
        context.user_data['ticket_list_status'] = status
        context.user_data['ticket_list_filter'] = query.data
        
        tickets = self.db.get_all_tickets(status=status)
        
        # Pagination
        page = 1
        pagination = self._paginate_tickets(tickets, page)
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        status_names = {
            'open': t('admin.tickets.list.header.open', lang),
            'in_progress': t('admin.tickets.list.header.in_progress', lang),
            'waiting_user': t('admin.tickets.list.header.waiting_user', lang),
            'resolved': t('admin.tickets.list.header.resolved', lang),
            None: t('admin.tickets.list.header.all', lang)
        }
        
        text = f"<b>{status_names.get(status)}</b>\n\n"
        
        if not tickets:
            text += t("admin.tickets.list.none", lang)
            keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")]]
        else:
            # نمایش اطلاعات صفحه
            text += t("admin.tickets.total", lang, n=pagination['total']) + "\n"
            text += t("pagination.page_of", lang, page=pagination['page'], total=pagination['total_pages']) + "\n"
            text += t("pagination.showing_range", lang, start=pagination['start_idx']+1, end=pagination['end_idx'], total=pagination['total']) + "\n\n"
            
            keyboard = []
            priority_icons = {'low': '🟢', 'medium': '🟡', 'high': '🔴', 'critical': '🚨'}
            
            for ticket in pagination['tickets']:
                ticket_id = ticket['id']
                subject = ticket['subject'][:30]
                priority = ticket.get('priority', 'medium')
                icon = priority_icons.get(priority, '⚪')
                
                button_text = f"{icon} #{ticket_id}: {subject}"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=f"adm_ticket_{ticket_id}")
                ])
            
            # دکمه‌های pagination
            nav_buttons = []
            if pagination['has_prev']:
                nav_buttons.append(InlineKeyboardButton(t("nav.prev", lang), callback_data=f"ticket_page_{page-1}"))
            if pagination['has_next']:
                nav_buttons.append(InlineKeyboardButton(t("nav.next", lang), callback_data=f"ticket_page_{page+1}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")])
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_tickets_page_navigation")
    async def admin_tickets_page_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت navigation بین صفحات"""
        query = update.callback_query
        await query.answer()
        
        page = int(query.data.split('_')[2])
        
        # دریافت status از context
        status = context.user_data.get('ticket_list_status')
        tickets = self.db.get_all_tickets(status=status)
        
        # Pagination
        pagination = self._paginate_tickets(tickets, page)
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        status_names = {
            'open': t('admin.tickets.list.header.open', lang),
            'in_progress': t('admin.tickets.list.header.in_progress', lang),
            'waiting_user': t('admin.tickets.list.header.waiting_user', lang),
            'resolved': t('admin.tickets.list.header.resolved', lang),
            None: t('admin.tickets.list.header.all', lang)
        }
        
        text = f"<b>{status_names.get(status)}</b>\n\n"
        text += t("admin.tickets.total", lang, n=pagination['total']) + "\n"
        text += t("pagination.page_of", lang, page=pagination['page'], total=pagination['total_pages']) + "\n"
        text += t("pagination.showing_range", lang, start=pagination['start_idx']+1, end=pagination['end_idx'], total=pagination['total']) + "\n\n"
        
        keyboard = []
        priority_icons = {'low': '🟢', 'medium': '🟡', 'high': '🔴', 'critical': '🚨'}
        
        for ticket in pagination['tickets']:
            ticket_id = ticket['id']
            subject = ticket['subject'][:30]
            priority = ticket.get('priority', 'medium')
            icon = priority_icons.get(priority, '⚪')
            
            button_text = f"{icon} #{ticket_id}: {subject}"
            keyboard.append([
                InlineKeyboardButton(button_text, callback_data=f"adm_ticket_{ticket_id}")
            ])
        
        # دکمه‌های navigation
        nav_buttons = []
        if pagination['has_prev']:
            nav_buttons.append(InlineKeyboardButton(t("nav.prev", lang), callback_data=f"ticket_page_{page-1}"))
        if pagination['has_next']:
            nav_buttons.append(InlineKeyboardButton(t("nav.next", lang), callback_data=f"ticket_page_{page+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_detail")
    async def admin_ticket_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش جزئیات تیکت"""
        query = update.callback_query
        await query.answer()
        
        ticket_id = int(query.data.split('_')[2])
        await self._show_ticket_detail(update, context, query, ticket_id)
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_reply_start")
    async def admin_ticket_reply_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع پاسخ به تیکت"""
        query = update.callback_query
        await query.answer()
        
        ticket_id = int(query.data.split('_')[2])
        context.user_data['ticket_reply_id'] = ticket_id
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        text = t("admin.tickets.reply.title", lang, id=ticket_id) + "\n\n" + t("admin.tickets.reply.prompt", lang)
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_tickets")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return TICKET_REPLY
    
    @log_admin_action("admin_ticket_reply_received")
    async def admin_ticket_reply_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت و ارسال پاسخ"""
        ticket_id = context.user_data.get('ticket_reply_id')
        admin_id = update.effective_user.id
        reply_text = update.message.text.strip()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if len(reply_text) < 5:
            await update.message.reply_text(t("admin.tickets.reply.too_short", lang))
            return TICKET_REPLY
        
        # ذخیره پاسخ
        success = self.db.add_ticket_reply(ticket_id, admin_id, reply_text, is_admin=True)
        
        # تغییر وضعیت به "منتظر کاربر"
        if success:
            self.db.update_ticket_status(ticket_id, 'waiting_user')
        
        # پاکسازی
        context.user_data.pop('ticket_reply_id', None)
        
        if success:
            # ارسال نوتیفیکیشن به کاربر
            ticket = self.db.get_ticket(ticket_id)
            try:
                # زبان کاربر را از DB بگیر
                try:
                    user_lang = self.db.get_user_language(ticket['user_id']) or 'fa'
                except Exception:
                    user_lang = 'fa'
                await context.bot.send_message(
                    chat_id=ticket['user_id'],
                    text=t('user.tickets.reply.received', user_lang, id=ticket_id, preview=reply_text[:100])
                )
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")
            
            await update.message.reply_text(t("admin.tickets.reply.sent", lang))
        else:
            await update.message.reply_text(t("admin.tickets.reply.error", lang))
        
        return await self.admin_tickets_menu(update, context)
    
    @log_admin_action("admin_ticket_change_status")
    async def admin_ticket_change_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تغییر وضعیت تیکت"""
        query = update.callback_query
        await query.answer()
        
        ticket_id = int(query.data.split('_')[2])
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        keyboard = [
            [InlineKeyboardButton(t("ticket.status.in_progress", lang), callback_data=f"adm_setstatus_{ticket_id}_in_progress")],
            [InlineKeyboardButton(t("ticket.status.waiting_user", lang), callback_data=f"adm_setstatus_{ticket_id}_waiting_user")],
            [InlineKeyboardButton(t("ticket.status.resolved", lang), callback_data=f"adm_setstatus_{ticket_id}_resolved")],
            [InlineKeyboardButton(t("ticket.status.closed", lang), callback_data=f"adm_setstatus_{ticket_id}_closed")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"adm_ticket_{ticket_id}")]
        ]
        
        await safe_edit_message_text(
            query,
            t("admin.tickets.status.title", lang, id=ticket_id) + "\n\n" + t("admin.tickets.status.prompt", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_set_status")
    async def admin_ticket_set_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """اعمال وضعیت جدید"""
        query = update.callback_query
        await query.answer()
        
        # Parse: adm_setstatus_123_in_progress -> ['adm', 'setstatus', '123', 'in_progress']
        # باید status رو از index 3 به بعد بگیریم
        parts = query.data.split('_')
        ticket_id = int(parts[2])
        new_status = '_'.join(parts[3:])  # برای status های multi-word مثل in_progress
        
        success = self.db.update_ticket_status(ticket_id, new_status)
        
        if success:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t("admin.tickets.status.changed", lang), show_alert=True)
            
            # ارسال notification به کاربر
            ticket = self.db.get_ticket(ticket_id)
            if ticket:
                await self._notify_user_status_change(context, ticket, new_status)
            
            # نمایش مجدد جزئیات تیکت با helper function
            await self._show_ticket_detail(update, context, query, ticket_id)
            return ADMIN_MENU
        else:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t("admin.tickets.status.error", lang), show_alert=True)
            return ADMIN_MENU
    
    @log_admin_action("admin_ticket_close")
    async def admin_ticket_close(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """بستن تیکت"""
        query = update.callback_query
        await query.answer()
        
        ticket_id = int(query.data.split('_')[2])
        
        success = self.db.update_ticket_status(ticket_id, 'closed')
        
        if success:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await safe_edit_message_text(
                query,
                t("admin.tickets.close.success", lang, id=ticket_id),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")]
                ])
            )
        else:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await safe_edit_message_text(query, t("admin.tickets.close.error", lang))
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_search_start")
    async def admin_ticket_search_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع جستجوی تیکت"""
        query = update.callback_query
        await query.answer()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = t("admin.tickets.search.title", lang) + "\n\n" + t("admin.tickets.search.prompt", lang)
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_tickets")]]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return TICKET_SEARCH
    
    @log_admin_action("admin_ticket_search_received")
    async def admin_ticket_search_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت متن جستجو و نمایش نتایج"""
        search_query = update.message.text.strip()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if len(search_query) < 2:
            await update.message.reply_text(t("admin.tickets.search.min_chars", lang))
            return TICKET_SEARCH
        
        # جستجو در تیکت‌ها
        tickets = self.db.search_tickets(search_query)
        
        text = t("admin.tickets.search.results", lang, query=html_escape(search_query)) + "\n\n"
        
        if not tickets:
            text += t("admin.tickets.search.none", lang)
            keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")]]
        else:
            text += t("admin.tickets.search.count", lang, n=len(tickets)) + "\n\n"
            
            keyboard = []
            priority_icons = {'low': '🟢', 'medium': '🟡', 'high': '🔴', 'critical': '🚨'}
            
            for ticket in tickets[:10]:  # نمایش 10 اول
                ticket_id = ticket['id']
                subject = ticket['subject'][:30]
                priority = ticket.get('priority', 'medium')
                icon = priority_icons.get(priority, '⚪')
                
                button_text = f"{icon} #{ticket_id}: {subject}"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=f"adm_ticket_{ticket_id}")
                ])
            
            if len(tickets) > 10:
                text += "\n" + t("admin.tickets.search.only_first_10", lang)
            
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")])
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_view_attachments")
    async def admin_ticket_view_attachments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش فایل‌های ضمیمه تیکت"""
        query = update.callback_query
        await query.answer()
        
        ticket_id = int(query.data.split('_')[2])
        ticket = self.db.get_ticket(ticket_id)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if not ticket:
            await safe_edit_message_text(query, t("admin.tickets.not_found", lang))
            return ADMIN_MENU
        
        # دریافت پاسخ‌ها برای یافتن attachments
        replies = self.db.get_ticket_replies(ticket_id)
        
        # جمع‌آوری attachments
        all_attachments = []
        
        # Attachments اصلی تیکت (به صورت list برگردانده می‌شود)
        if ticket.get('attachments'):
            if isinstance(ticket['attachments'], list):
                all_attachments.extend(ticket['attachments'])
            else:
                logger.warning(f"Ticket {ticket_id} attachments is not a list: {type(ticket['attachments'])}")
        
        # Attachments از replies
        for reply in replies:
            if reply.get('attachments'):
                if isinstance(reply['attachments'], list):
                    all_attachments.extend(reply['attachments'])
                else:
                    logger.warning(f"Reply attachments is not a list: {type(reply['attachments'])}")
        
        if not all_attachments:
            await safe_edit_message_text(
                query,
                t("admin.tickets.attachments.title", lang, id=ticket_id) + "\n\n" + t("admin.tickets.attachments.none", lang),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"adm_ticket_{ticket_id}")]
                ]),
                parse_mode='HTML'
            )
            return ADMIN_MENU
        
        # ارسال تمام تصاویر
        await safe_edit_message_text(
            query,
            t("admin.tickets.attachments.title", lang, id=ticket_id) + "\n\n" + t("admin.tickets.attachments.count", lang, n=len(all_attachments)),
            parse_mode='HTML'
        )
        
        for file_id in all_attachments[:10]:  # حداکثر 10 فایل
            try:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=file_id
                )
            except Exception as e:
                logger.error(f"Failed to send attachment {file_id}: {e}")
        
        # دکمه بازگشت
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=t("admin.tickets.attachments.done", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("admin.tickets.buttons.back_to_ticket", lang), callback_data=f"adm_ticket_{ticket_id}")]
            ])
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_change_priority")
    async def admin_ticket_change_priority(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تغییر اولویت تیکت"""
        query = update.callback_query
        await query.answer()
        
        ticket_id = int(query.data.split('_')[2])
        lang = get_user_lang(update, context, self.db) or 'fa'
        keyboard = [
            [InlineKeyboardButton(t("ticket.priority.low", lang), callback_data=f"adm_setpriority_{ticket_id}_low")],
            [InlineKeyboardButton(t("ticket.priority.medium", lang), callback_data=f"adm_setpriority_{ticket_id}_medium")],
            [InlineKeyboardButton(t("ticket.priority.high", lang), callback_data=f"adm_setpriority_{ticket_id}_high")],
            [InlineKeyboardButton(t("ticket.priority.critical", lang), callback_data=f"adm_setpriority_{ticket_id}_critical")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"adm_ticket_{ticket_id}")]
        ]
        
        await safe_edit_message_text(
            query,
            t("admin.tickets.priority.title", lang, id=ticket_id) + "\n\n" + t("admin.tickets.priority.prompt", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_set_priority")
    async def admin_ticket_set_priority(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """اعمال اولویت جدید"""
        query = update.callback_query
        await query.answer()
        
        parts = query.data.split('_')
        ticket_id = int(parts[2])
        new_priority = parts[3]
        
        success = self.db.update_ticket_priority(ticket_id, new_priority)
        
        if success:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t("admin.tickets.priority.changed", lang), show_alert=True)
            
            # ارسال notification به کاربر
            ticket = self.db.get_ticket(ticket_id)
            if ticket:
                await self._notify_user_priority_change(context, ticket, new_priority)
            
            await self._show_ticket_detail(update, context, query, ticket_id)
        else:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t("admin.tickets.priority.error", lang), show_alert=True)
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_assign_start")
    async def admin_ticket_assign_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع واگذاری تیکت"""
        query = update.callback_query
        await query.answer()
        
        ticket_id = int(query.data.split('_')[2])
        
        # دریافت لیست ادمین‌ها
        admins = self.db.get_all_admins()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if not admins:
            await safe_edit_message_text(
                query,
                t("admin.tickets.assign.none", lang),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"adm_ticket_{ticket_id}")]
                ])
            )
            return ADMIN_MENU
        
        keyboard = []
        for admin in admins[:10]:  # نمایش 10 ادمین اول
            admin_id = admin['user_id']
            display_name = admin.get('display_name') or admin.get('username') or f"User {admin_id}"
            keyboard.append([
                InlineKeyboardButton(
                    f"👤 {display_name}", 
                    callback_data=f"adm_doassign_{ticket_id}_{admin_id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"adm_ticket_{ticket_id}")])
        
        await safe_edit_message_text(
            query,
            t("admin.tickets.assign.title", lang, id=ticket_id),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_ticket_assign_confirm")
    async def admin_ticket_assign_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تایید واگذاری تیکت"""
        query = update.callback_query
        await query.answer()
        
        parts = query.data.split('_')
        ticket_id = int(parts[2])
        admin_id = int(parts[3])
        
        success = self.db.assign_ticket(ticket_id, admin_id)
        
        if success:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t("admin.tickets.assign.success", lang), show_alert=True)
            
            # ارسال notification به کاربر
            ticket = self.db.get_ticket(ticket_id)
            if ticket:
                await self._notify_user_assignment(context, ticket, admin_id)
            
            await self._show_ticket_detail(update, context, query, ticket_id)
        else:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t("admin.tickets.assign.error", lang), show_alert=True)
        
        return ADMIN_MENU
    
    @log_admin_action("admin_tickets_filter_category")
    async def admin_tickets_filter_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش فیلتر دسته‌بندی"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        categories = ['bug', 'feature_request', 'question', 'content_issue', 'channel_issue', 'other']
        
        keyboard = []
        for cat_key in categories:
            keyboard.append([
                InlineKeyboardButton(t(f"admin.tickets.category.{cat_key}", lang), callback_data=f"adm_tickets_cat_{cat_key}")
            ])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")])
        
        await safe_edit_message_text(
            query,
            t("admin.tickets.filter.title", lang) + "\n\n" + t("admin.tickets.filter.prompt", lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_tickets_by_category")
    async def admin_tickets_by_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش تیکت‌های یک دسته"""
        query = update.callback_query
        await query.answer()
        
        category = query.data.split('_')[3]
        
        # فیلتر بر اساس category
        all_tickets = self.db.get_all_tickets()
        tickets = [t for t in all_tickets if t.get('category') == category]
        
        # ذخیره برای pagination
        context.user_data['ticket_list_status'] = None
        context.user_data['ticket_list_category'] = category
        
        # Pagination
        page = 1
        pagination = self._paginate_tickets(tickets, page)
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = f"<b>{t(f'admin.tickets.category.{category}', lang)}</b>\n\n"
        
        if not tickets:
            text += t("admin.tickets.list.none", lang)
            keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="adm_tickets_filter_category")]]
        else:
            text += t("admin.tickets.total", lang, n=pagination['total']) + "\n"
            text += t("pagination.page_of", lang, page=pagination['page'], total=pagination['total_pages']) + "\n"
            text += t("pagination.showing_range", lang, start=pagination['start_idx']+1, end=pagination['end_idx'], total=pagination['total']) + "\n\n"
            
            keyboard = []
            priority_icons = {'low': '🟢', 'medium': '🟡', 'high': '🔴', 'critical': '🚨'}
            
            for ticket in pagination['tickets']:
                ticket_id = ticket['id']
                subject = ticket['subject'][:30]
                priority = ticket.get('priority', 'medium')
                icon = priority_icons.get(priority, '⚪')
                
                button_text = f"{icon} #{ticket_id}: {subject}"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=f"adm_ticket_{ticket_id}")
                ])
            
            # دکمه‌های pagination
            nav_buttons = []
            if pagination['has_prev']:
                nav_buttons.append(InlineKeyboardButton(t("nav.prev", lang), callback_data=f"ticket_page_{page-1}"))
            if pagination['has_next']:
                nav_buttons.append(InlineKeyboardButton(t("nav.next", lang), callback_data=f"ticket_page_{page+1}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="adm_tickets_filter_category")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
    
    @log_admin_action("admin_tickets_mine")
    async def admin_tickets_mine(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش تیکت‌های واگذار شده به من"""
        query = update.callback_query
        await query.answer()
        
        admin_id = update.effective_user.id
        
        # فیلتر بر اساس assigned_to
        tickets = self.db.get_all_tickets(assigned_to=admin_id)
        
        # ذخیره برای pagination
        context.user_data['ticket_list_status'] = None
        context.user_data['ticket_list_assigned'] = admin_id
        
        # Pagination
        page = 1
        pagination = self._paginate_tickets(tickets, page)
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = t("admin.tickets.mine.title", lang) + "\n\n"
        
        if not tickets:
            text += t("admin.tickets.mine.none", lang)
            keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")]]
        else:
            text += t("admin.tickets.total", lang, n=pagination['total']) + "\n"
            text += t("pagination.page_of", lang, page=pagination['page'], total=pagination['total_pages']) + "\n"
            text += t("pagination.showing_range", lang, start=pagination['start_idx']+1, end=pagination['end_idx'], total=pagination['total']) + "\n\n"
            
            keyboard = []
            priority_icons = {'low': '🟢', 'medium': '🟡', 'high': '🔴', 'critical': '🚨'}
            status_icons = {
                'open': '🆕',
                'in_progress': '⚙️',
                'waiting_user': '⏳',
                'resolved': '✅',
                'closed': '🔒'
            }
            
            for ticket in pagination['tickets']:
                ticket_id = ticket['id']
                subject = ticket['subject'][:25]
                priority = ticket.get('priority', 'medium')
                status = ticket.get('status', 'open')
                p_icon = priority_icons.get(priority, '⚪')
                s_icon = status_icons.get(status, '📝')
                
                button_text = f"{p_icon}{s_icon} #{ticket_id}: {subject}"
                keyboard.append([
                    InlineKeyboardButton(button_text, callback_data=f"adm_ticket_{ticket_id}")
                ])
            
            # دکمه‌های pagination
            nav_buttons = []
            if pagination['has_prev']:
                nav_buttons.append(InlineKeyboardButton(t("nav.prev", lang), callback_data=f"ticket_page_{page-1}"))
            if pagination['has_next']:
                nav_buttons.append(InlineKeyboardButton(t("nav.next", lang), callback_data=f"ticket_page_{page+1}"))
            
            if nav_buttons:
                keyboard.append(nav_buttons)
            
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")])
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADMIN_MENU
