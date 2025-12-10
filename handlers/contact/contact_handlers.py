"""
Handlers برای سیستم تماس با ما
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from managers.contact_system import ContactSystem, TicketCategory, TicketPriority
from utils.logger import get_logger, log_user_action
from utils.i18n import t
from utils.language import get_user_lang

logger = get_logger('contact_handlers', 'contact.log')

# States
(CONTACT_MENU, TICKET_CATEGORY, TICKET_SUBJECT, TICKET_DESCRIPTION, 
 TICKET_ATTACHMENT, FAQ_SEARCH, FEEDBACK_RATING, FEEDBACK_MESSAGE) = range(8)


class ContactHandlers:
    """مدیریت handlers تماس با ما"""
    
    def __init__(self, db):
        self.db = db
        self.contact_system = ContactSystem(db)
    
    async def search_cancel_and_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش منوی تماس"""
        from telegram.ext import ConversationHandler
        await self.contact_menu(update, context)
        return ConversationHandler.END
    
    async def contact_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی اصلی تماس با ما"""
        from datetime import datetime
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        query = update.callback_query if update.callback_query else None
        
        # چیدمان بهینه شده - 2 ستونی
        keyboard = [
            [
                InlineKeyboardButton(t("contact.menu.new_ticket", lang), callback_data="contact_new_ticket"),
                InlineKeyboardButton(t("contact.menu.my_tickets", lang), callback_data="contact_my_tickets")
            ],
            [
                InlineKeyboardButton(t("contact.menu.faq", lang), callback_data="contact_faq"),
                InlineKeyboardButton(t("contact.menu.feedback", lang), callback_data="contact_feedback")
            ]
        ]
        
        # اضافه کردن دکمه تماس مستقیم اگر فعال باشد
        direct_contact_enabled = self.db.get_setting('direct_contact_enabled', 'true')
        if direct_contact_enabled.lower() == 'true':
            contact_link = self.db.get_setting('direct_contact_link', 'https://t.me/YourSupportChannel')
            contact_name = self.db.get_setting('direct_contact_name', '💬 تماس مستقیم')
            keyboard.append([InlineKeyboardButton(contact_name, url=contact_link)])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")])
        
        # اضافه کردن timestamp برای جلوگیری از duplicate detection
        now = datetime.now().strftime("%H:%M:%S")
        
        text = (
            f"{t('contact.menu.title', lang)} {t('contact.menu.updated', lang, time=now)}\n\n"
            f"{t('contact.menu.desc', lang)}\n\n"
            f"{t('contact.menu.help_lines', lang)}"
        )
        
        if query:
            await query.answer()
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        return CONTACT_MENU


    # ==================== Ticket Handlers ====================
    
    async def new_ticket_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع فرآیند ثبت تیکت جدید"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        # چیدمان بهینه شده - 2 ستونی
        keyboard = [
            [
                InlineKeyboardButton(t('contact.ticket.category.bug', lang), callback_data="tc_bug"),
                InlineKeyboardButton(t('contact.ticket.category.feature_request', lang), callback_data="tc_feature_request")
            ],
            [
                InlineKeyboardButton(t('contact.ticket.category.question', lang), callback_data="tc_question"),
                InlineKeyboardButton(t('contact.ticket.category.content_issue', lang), callback_data="tc_content_issue")
            ],
            [
                InlineKeyboardButton(t('contact.ticket.category.channel_issue', lang), callback_data="tc_channel_issue"),
                InlineKeyboardButton(t('contact.ticket.category.other', lang), callback_data="tc_other")
            ],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")]
        ]
        
        text = t('contact.ticket.new.title', lang) + "\n\n" + t('contact.ticket.category.prompt', lang)
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return TICKET_CATEGORY
    
    async def ticket_category_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت دسته تیکت"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        category = query.data.replace("tc_", "")
        context.user_data['ticket_category'] = category
        
        category_name = ContactSystem.format_category_name(category)
        
        text = (
            t('contact.ticket.subject.title', lang) + "\n\n"
            + t('contact.ticket.subject.selected_category', lang, category=category_name) + "\n\n"
            + t('contact.ticket.subject.prompt', lang)
        )
        await query.edit_message_text(text, parse_mode='Markdown')
        return TICKET_SUBJECT
    
    async def ticket_subject_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت موضوع تیکت"""
        subject = update.message.text.strip()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if len(subject) < 5:
            await update.message.reply_text(t('contact.ticket.subject.too_short', lang, n=5))
            return TICKET_SUBJECT
        
        if len(subject) > 200:
            await update.message.reply_text(t('contact.ticket.subject.too_long', lang, n=200))
            return TICKET_SUBJECT
        
        context.user_data['ticket_subject'] = subject
        
        # پیشنهاد FAQ های مرتبط (بر اساس زبان کاربر)
        suggested_faqs = self.contact_system.get_suggested_faqs(subject, limit=3, lang=lang)
        
        if suggested_faqs:
            text = f"💡 **سوالات مشابه**\n\nقبل از ادامه، شاید این سوالات به شما کمک کنند:\n\n"

            keyboard = []
            for i, faq in enumerate(suggested_faqs, 1):
                text += f"{i}. {faq['question']}\n"
                keyboard.append([InlineKeyboardButton(t('contact.faq.view_answer', lang, i=i), callback_data=f"faq_view_{faq['id']}")])
            
            # lang مشخص شده در بالا
            keyboard.append([InlineKeyboardButton(t('nav.next', lang), callback_data="ticket_continue")])
            keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")])
            
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return TICKET_DESCRIPTION
        else:
            await update.message.reply_text(t('contact.ticket.description.prompt', lang), parse_mode='Markdown')
            return TICKET_DESCRIPTION
    
    async def ticket_continue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ادامه ثبت تیکت بعد از مشاهده FAQ"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.edit_message_text(t('contact.ticket.description.prompt', lang), parse_mode='Markdown')
        return TICKET_DESCRIPTION
    
    async def ticket_description_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت توضیحات تیکت"""
        description = update.message.text.strip()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if len(description) < 10:
            await update.message.reply_text(t('contact.ticket.description.too_short', lang, n=10))
            return TICKET_DESCRIPTION
        
        context.user_data['ticket_description'] = description
        
        keyboard = [
            [InlineKeyboardButton(t('contact.attachment.add_image', lang), callback_data="ticket_add_image")],
            [InlineKeyboardButton(t('contact.submit_without_image', lang), callback_data="ticket_submit")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")]
        ]
        
        text = t('contact.image.optional.title', lang)
        
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return TICKET_ATTACHMENT
    
    async def ticket_add_image_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """درخواست آپلود تصویر"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.edit_message_text(t('contact.image.send', lang), parse_mode='Markdown')
        return TICKET_ATTACHMENT
    
    async def ticket_image_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت تصویر"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not update.message.photo:
            await update.message.reply_text(t('contact.validation.image_required', lang))
            return TICKET_ATTACHMENT
        
        # ذخیره file_id بزرگترین عکس
        file_id = update.message.photo[-1].file_id
        
        if 'ticket_attachments' not in context.user_data:
            context.user_data['ticket_attachments'] = []
        
        context.user_data['ticket_attachments'].append(file_id)
        
        keyboard = [
            [InlineKeyboardButton(t('contact.image.add_more', lang), callback_data="ticket_add_image")],
            [InlineKeyboardButton(t('contact.submit.confirm', lang), callback_data="ticket_submit")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")]
        ]
        
        count = len(context.user_data['ticket_attachments'])
        text = t('contact.image.received', lang, count=count)
        
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return TICKET_ATTACHMENT
    
    async def ticket_submit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ثبت نهایی تیکت"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('contact.saving', lang))
        
        user_id = update.effective_user.id
        category = context.user_data.get('ticket_category')
        subject = context.user_data.get('ticket_subject')
        description = context.user_data.get('ticket_description')
        attachments = context.user_data.get('ticket_attachments', [])
        
        # ثبت تیکت
        ticket_id = self.contact_system.create_ticket(
            user_id=user_id,
            category=category,
            subject=subject,
            description=description,
            priority="medium",
            attachments=attachments
        )
        
        if ticket_id:
            text = t(
                'contact.ticket.submitted',
                lang,
                id=ticket_id,
                category=ContactSystem.format_category_name(category),
                subject=subject
            )
            # پاک کردن داده‌های موقت
            context.user_data.pop('ticket_category', None)
            context.user_data.pop('ticket_subject', None)
            context.user_data.pop('ticket_description', None)
            context.user_data.pop('ticket_attachments', None)
            
            # ارسال نوتیف به ادمین‌ها
            await self._notify_admins_new_ticket(context, ticket_id, category, subject, user_id)
            
        else:
            text = t('contact.ticket.error', lang)
        
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")]]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return CONTACT_MENU
    
    # ==================== My Tickets ====================
    
    async def my_tickets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش تیکت‌های کاربر"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        user_id = update.effective_user.id
        tickets = self.contact_system.get_user_tickets(user_id)
        
        if not tickets:
            text = t('contact.my_tickets.title', lang) + "\n\n" + t('contact.my_tickets.empty', lang)
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")]]
            
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return CONTACT_MENU
        
        text = t('contact.my_tickets.title', lang) + "\n\n"
        keyboard = []
        
        from validators import escape_markdown
        for ticket in tickets[:10]:  # نمایش 10 تیکت اخیر
            status_icon = "🆕" if ticket['status'] == 'open' else "⚙️" if ticket['status'] == 'in_progress' else "✅"
            subject_safe = escape_markdown(ticket['subject'][:30])
            text += f"{status_icon} `#{ticket['id']}` - {subject_safe}...\n"
            
            # برای دکمه، فقط کاراکترهای مشکل‌ساز رو پاک می‌کنیم
            subject_btn = ticket['subject'][:25].replace('_', ' ').replace('*', '').replace('[', '').replace(']', '')
            keyboard.append([InlineKeyboardButton(
                f"#{ticket['id']} - {subject_btn}",
                callback_data=f"ticket_view_{ticket['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return CONTACT_MENU
    
    async def view_ticket(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش جزئیات یک تیکت"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        ticket_id = int(query.data.replace("ticket_view_", ""))
        ticket = self.contact_system.get_ticket(ticket_id)
        
        if not ticket:
            await query.answer(t('contact.ticket.not_found', lang), show_alert=True)
            return CONTACT_MENU
        
        # بررسی مالکیت
        if ticket['user_id'] != update.effective_user.id:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t('error.unauthorized', lang), show_alert=True)
            return CONTACT_MENU
        
        # دریافت پاسخ‌ها
        replies = self.contact_system.get_ticket_replies(ticket_id)
        
        # Escape کردن محتوا برای Markdown
        from validators import escape_markdown
        subject_safe = escape_markdown(ticket['subject'])
        description_safe = escape_markdown(ticket['description'])
        category_name = escape_markdown(ContactSystem.format_category_name(ticket['category']))
        status_name = escape_markdown(ContactSystem.format_status_name(ticket['status']))
        priority_name = escape_markdown(ContactSystem.format_priority_name(ticket['priority']))
        
        text = f"""
🎫 **تیکت #{ticket_id}**

📂 دسته: {category_name}
📝 موضوع: {subject_safe}
📊 وضعیت: {status_name}
🎯 اولویت: {priority_name}
📅 تاریخ: {ticket['created_at'][:16]}

**توضیحات:**
{description_safe}

━━━━━━━━━━━━━━━
💬 **پاسخ‌ها ({len(replies)}):**
"""
        
        for reply in replies[-5:]:  # آخرین 5 پاسخ
            sender = "🔷 پشتیبانی" if reply['is_admin'] else "👤 شما"
            message_safe = escape_markdown(reply['message'])
            text += f"\n{sender} | {reply['created_at'][:16]}\n{message_safe}\n"
        
        keyboard = []
        
        if ticket['status'] not in ['closed', 'resolved']:
            keyboard.append([InlineKeyboardButton("💬 پاسخ دادن", callback_data=f"ticket_reply_{ticket_id}")])
        
        keyboard.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="contact_my_tickets")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return CONTACT_MENU
    
    # ==================== FAQ Handlers ====================
    
    async def faq_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی FAQ"""
        query = update.callback_query
        await query.answer()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        faqs = self.contact_system.get_faqs(lang=lang)
        
        text = t("contact.faq.title", lang) + "\n\n" + t("contact.faq.prompt", lang) + "\n\n"
        
        keyboard = []
        for faq in faqs[:10]:
            text += f"• {faq['question']}\n"
            keyboard.append([InlineKeyboardButton(
                faq['question'][:50] + "...",
                callback_data=f"faq_view_{faq['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton(t("contact.faq.buttons.search", lang), callback_data="faq_search")])
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="contact_menu")])
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return CONTACT_MENU
    
    async def faq_view(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش یک FAQ"""
        query = update.callback_query
        await query.answer()
        
        faq_id = int(query.data.replace("faq_view_", ""))
        
        # افزایش بازدید
        self.contact_system.increment_faq_views(faq_id)
        
        # دریافت FAQ بر اساس زبان کاربر
        lang = get_user_lang(update, context, self.db) or 'fa'
        faqs = self.contact_system.get_faqs(lang=lang)
        faq = next((f for f in faqs if f['id'] == faq_id), None)
        
        if not faq:
            await query.answer(t('common.not_found', lang), show_alert=True)
            return CONTACT_MENU
        
        # شمارنده‌های بازخورد (ممکن است not_helpful_count وجود نداشته باشد)
        helpful = faq.get('helpful_count', 0)
        not_helpful = faq.get('not_helpful_count', 0)
        text = (
            f"{t('contact.faq.view.question_label', lang)}\n{faq['question']}\n\n"
            f"{t('contact.faq.view.answer_label', lang)}\n{faq['answer']}\n\n"
            f"{t('contact.faq.view.views', lang, views=faq['views'])}\n"
            f"{t('contact.faq.view.helpful', lang, count=helpful)}   |   {t('contact.faq.view.not_helpful', lang, count=not_helpful)}"
        )
        
        keyboard = [
            [InlineKeyboardButton(t("contact.faq.buttons.helpful", lang), callback_data=f"faq_helpful_{faq_id}"),
             InlineKeyboardButton(t("contact.faq.buttons.not_helpful", lang), callback_data=f"faq_not_helpful_{faq_id}")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="contact_faq")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return CONTACT_MENU
    
    @log_user_action("faq_mark_helpful")
    async def faq_mark_helpful(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ثبت رای مفید برای FAQ و به‌روزرسانی UI"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        try:
            faq_id = int(query.data.replace("faq_helpful_", ""))
        except Exception:
            await query.answer(t('contact.faq.vote.error', lang), show_alert=True)
            return CONTACT_MENU
        # رأی کاربر (هر کاربر حداکثر یک رأی، قابلیت تغییر/حذف)
        user_id = update.effective_user.id
        result = self.contact_system.vote_faq(user_id, faq_id, helpful=True)
        if result.get('success'):
            action = result.get('action')
            if action == 'added':
                msg = t('contact.faq.vote.helpful.added', lang)
            elif action == 'removed':
                msg = t('contact.faq.vote.helpful.removed', lang)
            elif action == 'changed':
                msg = t('contact.faq.vote.helpful.changed', lang)
            else:
                msg = t('contact.faq.vote.saved', lang)
            await query.answer(msg, show_alert=False)
        else:
            await query.answer(t('contact.faq.vote.error', lang), show_alert=True)
        await self._refresh_faq_message(query, faq_id, lang)
        return CONTACT_MENU
    
    @log_user_action("faq_mark_not_helpful")
    async def faq_mark_not_helpful(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ثبت رای نامفید برای FAQ و به‌روزرسانی UI"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        try:
            faq_id = int(query.data.replace("faq_not_helpful_", ""))
        except Exception:
            await query.answer(t('contact.faq.vote.error', lang), show_alert=True)
            return CONTACT_MENU
        user_id = update.effective_user.id
        result = self.contact_system.vote_faq(user_id, faq_id, helpful=False)
        if result.get('success'):
            action = result.get('action')
            if action == 'added':
                msg = t('contact.faq.vote.not_helpful.added', lang)
            elif action == 'removed':
                msg = t('contact.faq.vote.not_helpful.removed', lang)
            elif action == 'changed':
                msg = t('contact.faq.vote.not_helpful.changed', lang)
            else:
                msg = t('contact.faq.vote.saved', lang)
            await query.answer(msg, show_alert=False)
        else:
            await query.answer(t('contact.faq.vote.error', lang), show_alert=True)
        lang = get_user_lang(update, context, self.db) or 'fa'
        await self._refresh_faq_message(query, faq_id, lang)
        return CONTACT_MENU
    
    async def _refresh_faq_message(self, query, faq_id: int, lang: str):
        """به‌روزرسانی متن و دکمه‌های FAQ پس از ثبت رای"""
        try:
            faqs = self.contact_system.get_faqs(lang=lang)
            faq = next((f for f in faqs if f.get('id') == faq_id), None)
            if not faq:
                return
            helpful = faq.get('helpful_count', 0)
            not_helpful = faq.get('not_helpful_count', 0)
            text = (
                f"{t('contact.faq.view.question_label', lang)}\n{faq['question']}\n\n"
                f"{t('contact.faq.view.answer_label', lang)}\n{faq['answer']}\n\n"
                f"{t('contact.faq.view.views', lang, views=faq['views'])}\n"
                f"{t('contact.faq.view.helpful', lang, count=helpful)}   |   {t('contact.faq.view.not_helpful', lang, count=not_helpful)}"
            )
            keyboard = [
                [InlineKeyboardButton(t("contact.faq.buttons.helpful", lang), callback_data=f"faq_helpful_{faq_id}"),
                 InlineKeyboardButton(t("contact.faq.buttons.not_helpful", lang), callback_data=f"faq_not_helpful_{faq_id}")],
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="contact_faq")]
            ]
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except Exception:
            # در صورت بروز خطا در رفرش UI، سکوت می‌کنیم تا تجربه کاربر مختل نشود
            try:
                await query.answer()
            except Exception:
                pass
    
    # ==================== Feedback Handlers ====================
    
    async def feedback_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع ثبت بازخورد"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        text = t('contact.feedback.title', lang) + "\n\n" + t('contact.feedback.choose_rating', lang)
        
        keyboard = [
            [InlineKeyboardButton("⭐⭐⭐⭐⭐", callback_data="feedback_rate_5"),
             InlineKeyboardButton("⭐⭐⭐⭐", callback_data="feedback_rate_4")],
            [InlineKeyboardButton("⭐⭐⭐", callback_data="feedback_rate_3"),
             InlineKeyboardButton("⭐⭐", callback_data="feedback_rate_2")],
            [InlineKeyboardButton("⭐", callback_data="feedback_rate_1")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return FEEDBACK_RATING
    
    async def feedback_rating_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت امتیاز"""
        query = update.callback_query
        await query.answer()
        
        rating = int(query.data.replace("feedback_rate_", ""))
        context.user_data['feedback_rating'] = rating
        
        stars = "⭐" * rating
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = f"{stars}\n\n" + t('contact.feedback.message.prompt', lang) + "\n\n" + t('contact.feedback.message.hint', lang)
        
        keyboard = [[InlineKeyboardButton(t('contact.feedback.submit_no_comment', lang), callback_data="feedback_submit_no_comment")]]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return FEEDBACK_MESSAGE
    
    async def feedback_message_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت پیام بازخورد"""
        message = update.message.text.strip()
        context.user_data['feedback_message'] = message
        
        return await self._submit_feedback(update, context)
    
    async def feedback_submit_no_comment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ثبت بدون نظر"""
        return await self._submit_feedback(update, context)
    
    async def _submit_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ثبت نهایی بازخورد"""
        user_id = update.effective_user.id
        rating = context.user_data.get('feedback_rating')
        message = context.user_data.get('feedback_message', "")
        
        success = self.contact_system.submit_feedback(
            user_id=user_id,
            rating=rating,
            category="general",
            message=message
        )
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        if success:
            text = t('contact.feedback.submit.success', lang)
        else:
            text = t('contact.feedback.submit.error', lang)
        
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="contact_menu")]]
        
        # پاک کردن داده‌های موقت
        context.user_data.pop('feedback_rating', None)
        context.user_data.pop('feedback_message', None)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        return CONTACT_MENU
    
    # ==================== Helper Methods ====================
    
    async def _notify_admins_new_ticket(self, context, ticket_id: int, category: str, subject: str, user_id: int):
        """ارسال نوتیفیکیشن به ادمین‌ها برای تیکت جدید"""
        try:
            # دریافت لیست ادمین‌های با دسترسی MANAGE_TICKETS
            from role_manager import RoleManager, Permission
            from validators import escape_markdown
            role_manager = RoleManager(self.db)
            
            # دریافت تمام ادمین‌ها
            admins = self.db.get_all_admins()
            
            # Escape کردن محتوا
            subject_safe = escape_markdown(subject)
            
            notification_text = f"""
🎫 **تیکت جدید ثبت شد**

📋 شماره: #{ticket_id}
👤 کاربر: `{user_id}`
📂 دسته: {ContactSystem.format_category_name(category)}
📝 موضوع: {subject_safe}

برای مشاهده جزئیات به پنل ادمین مراجعه کنید.
"""
            
            # ساخت کیبورد با دکمه مشاهده تیکت
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton("🔍 مشاهده تیکت", callback_data=f"adm_ticket_{ticket_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # ارسال به تمام ادمین‌ها
            for admin in admins:
                admin_id = admin.get('user_id')
                # بررسی دسترسی
                if role_manager.has_permission(admin_id, Permission.MANAGE_TICKETS):
                    try:
                        await context.bot.send_message(
                            chat_id=admin_id,
                            text=notification_text,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                        logger.info(f"Ticket notification sent to admin {admin_id}")
                    except Exception as e:
                        logger.error(f"Error sending notification to admin {admin_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error in _notify_admins_new_ticket: {e}")
