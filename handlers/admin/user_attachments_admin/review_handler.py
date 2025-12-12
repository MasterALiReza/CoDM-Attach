"""
Review Handler - بررسی و تایید/رد اتچمنت‌های کاربران
"""

from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.error import BadRequest
from telegram.helpers import escape_markdown
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from config.config import GAME_MODES
from core.database.database_adapter import get_database_adapter
from core.security.role_manager import RoleManager, Permission
from core.cache.ua_cache_manager import get_ua_cache
from utils.logger import get_logger
from utils.i18n import t
from utils.language import get_user_lang
import time

logger = get_logger('ua_admin', 'admin.log')
db = get_database_adapter()
role_manager = RoleManager(db)
cache = get_ua_cache(db, ttl_seconds=300)

# States
UA_ADMIN_REJECT_REASON = 1
UA_ADMIN_EDIT_WEAPON = 2

# تعداد اتچمنت در هر صفحه
PENDING_PER_PAGE = 10


def check_ua_admin_permission(user_id: int) -> bool:
    """بررسی دسترسی مدیریت اتچمنت کاربران"""
    # Permission-based: allow SuperAdmin or MANAGE_USER_ATTACHMENTS
    try:
        if role_manager.is_super_admin(user_id):
            return True
        return role_manager.has_permission(user_id, Permission.MANAGE_USER_ATTACHMENTS)
    except Exception:
        # Fallback برای سازگاری قدیمی
        return db.is_admin(user_id)


async def show_ua_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی اصلی مدیریت اتچمنت کاربران"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not check_ua_admin_permission(user_id):
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    # دریافت آمار - OPTIMIZED VERSION
    try:
        start_time = time.time()
        
        # روش 1: تلاش برای خواندن از ua_stats_realtime
        if hasattr(db, 'get_connection'):
            try:
                with db.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT * FROM ua_stats_realtime WHERE id = 1")
                    result = cursor.fetchone()
                    if result:
                        pending_count = int((result or {}).get('pending_count') or 0)
                        approved_count = int((result or {}).get('approved_count') or 0)
                        rejected_count = int((result or {}).get('rejected_count') or 0)
                        banned_count = int((result or {}).get('banned_users') or 0)
                        # محاسبه گزارش‌های معلق به صورت جداگانه
                        cursor.execute("SELECT COUNT(*) AS cnt FROM user_attachment_reports WHERE status = 'pending'")
                        rc = cursor.fetchone()
                        reports_count = int((rc or {}).get('cnt') or 0)
                        logger.debug("Stats loaded from ua_stats_realtime table")
                    else:
                        raise RuntimeError("ua_stats_realtime empty")
            except Exception as realtime_err:
                # اگر جدول وجود ندارد یا خطا داشت، به cache و سپس fallback مستقیم برو
                logger.debug(f"ua_stats_realtime unavailable: {realtime_err}")
                stats = cache.get_stats()
                if stats:
                    pending_count = stats.get('pending_count', 0)
                    approved_count = stats.get('approved_count', 0)
                    rejected_count = stats.get('rejected_count', 0)
                    banned_count = stats.get('banned_users', 0)
                    reports_count = stats.get('pending_reports', 0)
                    try:
                        with db.get_connection() as conn:
                            c2 = conn.cursor()
                            c2.execute("SELECT COUNT(*) AS cnt FROM user_attachment_reports WHERE status = 'pending'")
                            r2 = c2.fetchone()
                            reports_count = int((r2 or {}).get('cnt') or 0)
                    except Exception:
                        pass
                else:
                    with db.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            SELECT 
                                (SELECT COUNT(*) FROM user_attachments WHERE status = 'pending') as pending_count,
                                (SELECT COUNT(*) FROM user_attachments WHERE status = 'approved') as approved_count,
                                (SELECT COUNT(*) FROM user_attachments WHERE status = 'rejected') as rejected_count,
                                (SELECT COUNT(*) FROM user_submission_stats WHERE is_banned = TRUE) as banned_count
                            """
                        )
                        result = cursor.fetchone()
                        pending_count = int(result.get('pending_count', 0))
                        approved_count = int(result.get('approved_count', 0))
                        rejected_count = int(result.get('rejected_count', 0))
                        banned_count = int(result.get('banned_count', 0))
                        # محاسبه تعداد گزارش‌ها در fallback مستقیم
                        cursor.execute("SELECT COUNT(*) AS cnt FROM user_attachment_reports WHERE status = 'pending'")
                        row = cursor.fetchone()
                        reports_count = int(row.get('cnt', 0))
        else:
            # اگر connection نبود، از cache استفاده کن
            stats = cache.get_stats()
            pending_count = stats.get('pending_count', 0) if stats else 0
            approved_count = stats.get('approved_count', 0) if stats else 0
            rejected_count = stats.get('rejected_count', 0) if stats else 0
            banned_count = stats.get('banned_users', 0) if stats else 0
            reports_count = stats.get('pending_reports', 0) if stats else 0
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"UA admin menu stats loaded in {elapsed:.2f}ms")
        
    except Exception as e:
        logger.error(f"Error getting UA admin stats: {e}")
        pending_count = 0
        approved_count = 0
        rejected_count = 0
        banned_count = 0
        reports_count = 0
    
    # محاسبه تعداد کلی اتچمنت‌ها
    total_count = pending_count + approved_count + rejected_count
    
    lang = get_user_lang(update, context, db) or 'fa'
    message = (
        t('admin.ua.menu.title', lang) + "\n\n"
        + t('admin.ua.menu.stats.header', lang) + "\n"
        + t('admin.ua.menu.stats.total', lang, n=total_count) + "\n"
        + t('admin.ua.menu.stats.pending', lang, n=pending_count) + "\n"
        + t('admin.ua.menu.stats.approved', lang, n=approved_count) + "\n"
        + t('admin.ua.menu.stats.rejected', lang, n=rejected_count) + "\n\n"
        + t('admin.ua.menu.stats.banned', lang, n=banned_count) + "\n"
        + t('admin.ua.menu.stats.reports', lang, n=reports_count)
    )
    
    keyboard = []
    
    # دکمه‌های بررسی
    if pending_count > 0:
        keyboard.append([InlineKeyboardButton(
            t('admin.ua.buttons.review_pending', lang, n=pending_count),
            callback_data="ua_admin_pending"
        )])
    
    # دکمه‌های مشاهده لیست‌ها
    keyboard.append([
        InlineKeyboardButton(t('admin.ua.buttons.approved', lang, n=approved_count), callback_data="ua_admin_approved"),
        InlineKeyboardButton(t('admin.ua.buttons.rejected', lang, n=rejected_count), callback_data="ua_admin_rejected")
    ])
    
    # دکمه‌های مدیریتی
    management_buttons = []
    
    # نمایش دکمه گزارش‌ها همیشه با تعداد فعلی (حتی اگر صفر باشد)
    management_buttons.append(InlineKeyboardButton(
        t('admin.ua.buttons.reports', lang, n=reports_count),
        callback_data="ua_admin_reports"
    ))
    
    if banned_count > 0:
        management_buttons.append(InlineKeyboardButton(
            t('admin.ua.buttons.banned', lang, n=banned_count),
            callback_data="ua_admin_banned"
        ))
    
    # اضافه دکمه‌های مدیریتی به ترتیب در یک یا دو ردیف
    if len(management_buttons) == 2:
        keyboard.append(management_buttons)
    elif len(management_buttons) == 1:
        keyboard.append(management_buttons)
    
    # دکمه‌های آمار و تنظیمات
    keyboard.append([
        InlineKeyboardButton(t('admin.ua.buttons.stats', lang), callback_data="ua_admin_stats"),
        InlineKeyboardButton(t('admin.ua.buttons.settings', lang), callback_data="ua_admin_settings")
    ])
    
    # دکمه بازگشت
    keyboard.append([InlineKeyboardButton(t('admin.ua.buttons.back_admin', lang), callback_data="admin_back")])
    
    try:
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        # اگه پیام photo بود
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete UA admin menu message: {e}")
        await update.effective_chat.send_message(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_pending_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست اتچمنت‌های pending"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not check_ua_admin_permission(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    # دریافت صفحه
    page = 0
    if 'page_' in query.data:
        page = int(query.data.split('_')[-1])
    
    # دریافت pending attachments با batch user loading
    try:
        start_time = time.time()
        
        # استفاده از cache برای COUNT
        total = cache.get_paginated_count('pending')
        
        # دریافت لیست
        pending = db.get_user_attachments_by_status('pending', limit=PENDING_PER_PAGE, offset=page * PENDING_PER_PAGE)
        
        # Batch load user data برای جلوگیری از N+1 queries
        if pending:
            user_ids = [att['user_id'] for att in pending]
            users_data = cache.batch_get_users(user_ids)
            for att in pending:
                user_info = users_data.get(att['user_id'], {})
                if not att.get('username'):
                    att['username'] = user_info.get('username', t('user.anonymous', lang))
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Pending list loaded in {elapsed:.2f}ms")
    except Exception as e:
        logger.error(f"Error fetching pending attachments: {e}")
        pending = []
        total = 0
    
    if not pending:
        try:
            await query.edit_message_text(
                t('admin.ua.pending.empty_title', lang) + "\n\n" + t('admin.ua.pending.empty_desc', lang),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")
                ]])
            )
        except Exception:
            # اگه پیام photo بود
            try:
                await query.message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete UA admin pending-empty message: {e}")
            await update.effective_chat.send_message(
                t('admin.ua.pending.empty_title', lang) + "\n\n" + t('admin.ua.pending.empty_desc', lang),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")
                ]])
            )
        return
    
    total_pages = (total - 1) // PENDING_PER_PAGE + 1
    
    message = (
        t('admin.ua.pending.title', lang) + "\n\n"
        + t('admin.ua.pending.header', lang, total=total, page=page + 1, total_pages=total_pages) + "\n\n"
        + t('admin.ua.pending.prompt', lang)
    )
    
    keyboard = []
    for att in pending:
        mode_icon = "🎮" if att['mode'] == 'mp' else "🪂"
        username = att.get('username', t('user.anonymous', lang))
        weapon_name = att.get('custom_weapon_name', att.get('weapon_name', t('common.unknown', lang)))
        att_name = att.get('name', att.get('attachment_name', t('attachment.name', lang)))
        
        keyboard.append([
            InlineKeyboardButton(
                f"{mode_icon} [{weapon_name}] {att_name[:20]} - @{username}",
                callback_data=f"ua_admin_review_{att['id']}"
            )
        ])
    
    # Pagination
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(t('nav.prev', lang), callback_data=f"ua_admin_pending_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(t('nav.next', lang), callback_data=f"ua_admin_pending_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")])
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_attachment_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات اتچمنت برای بررسی"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not check_ua_admin_permission(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    # دریافت اتچمنت و آمار کاربر همزمان (optimize با JOIN در آینده)
    start_time = time.time()
    attachment = db.get_user_attachment(int(query.data.replace('ua_admin_review_', '')))
    
    if not attachment:
        await query.answer(t('attachment.not_found', lang), show_alert=True)
        return
    
    # دریافت آمار کاربر
    stats = db.get_user_submission_stats(attachment['user_id'])
    
    elapsed = (time.time() - start_time) * 1000
    logger.info(f"Attachment review loaded in {elapsed:.2f}ms")
    
    # ساخت پیام
    mode_name = t(f"mode.{attachment['mode']}_short", lang)
    username = attachment.get('username', t('user.anonymous', lang))
    description = attachment.get('description') or t('common.no_description', lang)
    
    # نمایش نام سلاح (custom یا از DB)
    weapon_display = attachment.get('custom_weapon_name') or attachment.get('weapon_name', t('common.unknown', lang))
    category_display = attachment.get('category', attachment.get('category_name', t('common.unknown', lang)))
    att_name = attachment.get('name', attachment.get('attachment_name', t('attachment.name', lang)))
    
    # Escape برای HTML
    from html import escape as html_escape
    weapon_display = html_escape(str(weapon_display))
    att_name = html_escape(str(att_name))
    description = html_escape(str(description))
    category_display = html_escape(str(category_display))
    mode_name = html_escape(str(mode_name))
    username = html_escape(str(username))
    
    # Safe date formatting for submitted_at
    sub_at = attachment.get('submitted_at')
    if isinstance(sub_at, datetime):
        submitted_date = sub_at.date().isoformat()
    elif isinstance(sub_at, date):
        submitted_date = sub_at.isoformat()
    else:
        submitted_date = str(sub_at)[:10]
    
    # Format strike count
    strike_count = f"{stats['strike_count']:.1f}"
    
    caption = (
        t('admin.ua.review.title', lang) + "\n\n"
        + f"📎 <b>{t('attachment.name', lang)}:</b> {att_name}\n"
        + f"🎮 <b>{t('mode.label', lang)}:</b> {mode_name}\n"
        + f"🔫 <b>{t('weapon.label', lang)}:</b> {weapon_display}\n"
        + f"📂 <b>{t('category.label', lang)}:</b> {category_display}\n"
        + f"💬 <b>{t('description.label', lang)}:</b>\n{description}\n\n"
        + f"<b>{t('admin.ua.review.user_header', lang)}</b>\n"
        + f"@{username}\n"
        + t('admin.ua.review.user_id', lang, id=attachment['user_id']) + "\n"
        + t('admin.ua.review.submitted_at', lang, date=submitted_date) + "\n\n"
        + f"<b>{t('admin.ua.review.user_stats', lang)}</b>\n"
        + t('admin.ua.review.stats.total', lang, n=stats['total_submissions']) + "\n"
        + t('admin.ua.review.stats.approved', lang, n=stats.get('approved_submissions', stats.get('approved_count', 0))) + "\n"
        + t('admin.ua.review.stats.rejected', lang, n=stats.get('rejected_submissions', stats.get('rejected_count', 0))) + "\n"
        + t('admin.ua.review.stats.strikes', lang, strikes=strike_count)
    )
    
    if stats['is_banned']:
        banned_reason = html_escape(stats.get('banned_reason', ''))
        caption += f"\n🚫 <b>{t('admin.ua.review.banned', lang)}:</b> {banned_reason}"
    
    keyboard = [
        [
            InlineKeyboardButton(t('admin.ua.buttons.approve', lang), callback_data=f"ua_admin_approve_{attachment['id']}"),
            InlineKeyboardButton(t('admin.ua.buttons.reject', lang), callback_data=f"ua_admin_reject_{attachment['id']}")
        ],
        [InlineKeyboardButton(t('admin.ua.buttons.edit_weapon_name', lang), callback_data=f"ua_admin_edit_weapon_{attachment['id']}")],
        [InlineKeyboardButton(t('admin.ua.buttons.ban_user', lang), callback_data=f"ua_admin_ban_{attachment['user_id']}")],
        [InlineKeyboardButton(t('admin.ua.buttons.back_to_list', lang), callback_data="ua_admin_pending")]
    ]
    
    # ارسال تصویر
    await query.message.reply_photo(
        photo=attachment['image_file_id'],
        caption=caption,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # حذف پیام قبلی
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete UA admin review source message: {e}")


async def approve_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید اتچمنت"""
    query = update.callback_query
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not check_ua_admin_permission(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    attachment_id = int(query.data.replace('ua_admin_approve_', ''))
    
    # دریافت اتچمنت
    attachment = db.get_user_attachment(attachment_id)
    
    if not attachment or attachment['status'] != 'pending':
        await query.answer(t('attachment.not_found', lang), show_alert=True)
        return
    
    # تایید
    success = db.approve_user_attachment(attachment_id, user_id)
    
    if success:
        # به‌روزرسانی آمار
        db.update_submission_stats(
            user_id=attachment['user_id'],
            increment_total=False  # قبلاً اضافه شده
        )
        
        # Invalidate cache after approval
        cache.invalidate('stats')
        cache.invalidate('count_pending')
        cache.invalidate('count_approved')
        
        # Notification به کاربر
        try:
            user_lang = None
            try:
                user_lang = db.get_user_language(attachment['user_id']) or 'fa'
            except Exception:
                user_lang = 'fa'
            mode_name = t(f"mode.{attachment['mode']}_short", user_lang)
            await context.bot.send_message(
                chat_id=attachment['user_id'],
                text=t('user.ua.approved', user_lang, name=attachment['attachment_name'], weapon=attachment['weapon_name'], mode=mode_name),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error sending approval notification: {e}")
        
        await query.answer(t('admin.ua.approve.success', lang), show_alert=True)
        
        # حذف تصویر
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete UA admin approved image message: {e}")
        
        # بررسی آیا هنوز اتچمنت pending دیگه‌ای هست
        try:
            remaining_count = cache.get_paginated_count('pending')
        except Exception as e:
            logger.error(f"Failed to get remaining pending attachments count from cache: {e}")
            remaining_count = 0
        
        if remaining_count > 0:
            # بازگشت به لیست pending
            context.user_data['temp_query_data'] = 'ua_admin_pending'
            await show_pending_list(update, context)
        else:
            # بازگشت به منوی اصلی
            await show_ua_admin_menu(update, context)
    else:
        await query.answer(t('error.generic', lang), show_alert=True)


async def start_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع فرآیند رد اتچمنت"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not check_ua_admin_permission(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return ConversationHandler.END
    
    attachment_id = int(query.data.replace('ua_admin_reject_', ''))
    context.user_data['ua_reject_attachment_id'] = attachment_id
    
    try:
        await query.edit_message_caption(
            caption=(
                query.message.caption + "\n\n"
                + t('admin.ua.reject.title', lang) + "\n\n"
                + t('admin.ua.reject.prompt', lang) + "\n"
                + t('admin.ua.reject.limit', lang) + "\n\n"
                + t('admin.ua.reject.cancel_hint', lang)
            ),
            parse_mode='Markdown'
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
    # پاک کردن ReplyKeyboard کاربر تا متن به همین مکالمه برسد
    try:
        await query.message.reply_text(t('admin.ua.reject.type_reason', lang), reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass
    
    return UA_ADMIN_REJECT_REASON


async def receive_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت دلیل رد"""
    reason = update.message.text.strip()
    
    lang = get_user_lang(update, context, db) or 'fa'
    if len(reason) > 200:
        await update.message.reply_text(
            t('admin.ua.reject.too_long', lang)
        )
        return UA_ADMIN_REJECT_REASON
    
    attachment_id = context.user_data.get('ua_reject_attachment_id')
    admin_id = update.effective_user.id
    
    # دریافت اتچمنت
    attachment = db.get_user_attachment(attachment_id)
    
    if not attachment:
        await update.message.reply_text(t('attachment.not_found', lang))
        return ConversationHandler.END
    
    # رد اتچمنت
    success = db.reject_user_attachment(attachment_id, admin_id, reason)
    
    # Invalidate cache after rejection
    if success:
        cache.invalidate('stats')
        cache.invalidate('count_pending')
        cache.invalidate('count_rejected')
    
    if success:
        # Notification به کاربر
        try:
            user_lang = None
            try:
                user_lang = db.get_user_language(attachment['user_id']) or 'fa'
            except Exception:
                user_lang = 'fa'
            mode_name = t(f"mode.{attachment['mode']}_short", user_lang)
            await context.bot.send_message(
                chat_id=attachment['user_id'],
                text=t('user.ua.rejected', user_lang, name=attachment['attachment_name'], weapon=attachment['weapon_name'], mode=mode_name, reason=reason),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error sending rejection notification: {e}")
        
        await update.message.reply_text(
            t('admin.ua.reject.success', lang),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_pending")
            ]])
        )
    else:
        await update.message.reply_text(t('admin.ua.reject.error', lang))
    
    # پاک کردن داده‌ها
    context.user_data.pop('ua_reject_attachment_id', None)
    
    return ConversationHandler.END


async def cancel_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو فرآیند رد"""
    lang = get_user_lang(update, context, db) or 'fa'
    await update.message.reply_text(
        t('common.cancelled', lang),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_pending")
        ]])
    )
    
    context.user_data.pop('ua_reject_attachment_id', None)
    return ConversationHandler.END


async def start_edit_weapon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش نام سلاح"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not check_ua_admin_permission(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return ConversationHandler.END
    
    attachment_id = int(query.data.replace('ua_admin_edit_weapon_', ''))
    
    # دریافت اتچمنت
    attachment = db.get_user_attachment(attachment_id)
    
    if not attachment:
        await query.answer(t('attachment.not_found', lang), show_alert=True)
        return ConversationHandler.END
    
    context.user_data['ua_edit_weapon_attachment_id'] = attachment_id
    
    current_weapon = attachment.get('custom_weapon_name', t('common.unknown', lang))
    
    try:
        await query.edit_message_caption(
            caption=(
                t('admin.ua.edit_weapon.title', lang) + "\n\n"
                + t('admin.ua.edit_weapon.current', lang, current=current_weapon) + "\n\n"
                + t('admin.ua.edit_weapon.prompt', lang) + "\n\n"
                + t('admin.ua.edit_weapon.rules', lang) + "\n\n"
                + t('admin.ua.reject.cancel_hint', lang)
            ),
            parse_mode='Markdown'
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise
    # پاک کردن ReplyKeyboard کاربر تا متن به همین مکالمه برسد
    try:
        await query.message.reply_text(t('admin.ua.edit_weapon.type_new', lang), reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass
    
    return UA_ADMIN_EDIT_WEAPON


async def receive_new_weapon_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت نام جدید سلاح"""
    weapon_name = update.message.text.strip()
    attachment_id = context.user_data.get('ua_edit_weapon_attachment_id')
    
    lang = get_user_lang(update, context, db) or 'fa'
    if not attachment_id:
        await update.message.reply_text(t('error.generic', lang))
        return ConversationHandler.END
    
    # Validation
    import re
    if len(weapon_name) < 2:
        await update.message.reply_text(
            t('admin.ua.edit_weapon.too_short', lang)
        )
        return UA_ADMIN_EDIT_WEAPON
    
    if len(weapon_name) > 30:
        await update.message.reply_text(
            t('admin.ua.edit_weapon.too_long', lang)
        )
        return UA_ADMIN_EDIT_WEAPON
    
    if not re.match(r'^[a-zA-Z0-9\s\-]+$', weapon_name):
        await update.message.reply_text(
            t('admin.ua.edit_weapon.invalid', lang)
        )
        return UA_ADMIN_EDIT_WEAPON
    
    # آپدیت در دیتابیس
    try:
        with db.transaction() as tconn:
            cur = tconn.cursor()
            cur.execute(
                """
                UPDATE user_attachments 
                SET custom_weapon_name = %s
                WHERE id = %s
                """,
                (weapon_name, attachment_id),
            )
        
        await update.message.reply_text(
            t('admin.ua.edit_weapon.updated', lang, new=weapon_name),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t('admin.ua.buttons.back_to_review', lang), callback_data=f"ua_admin_review_{attachment_id}")
            ]])
        )
        
        logger.info(f"Weapon name updated for attachment {attachment_id}: {weapon_name}")
    
    except Exception as e:
        logger.error(f"Error updating weapon name: {e}")
        await update.message.reply_text(t('admin.ua.edit_weapon.error', lang))
    
    # پاک کردن داده‌ها
    context.user_data.pop('ua_edit_weapon_attachment_id', None)
    
    return ConversationHandler.END


async def cancel_edit_weapon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو ویرایش نام سلاح"""
    attachment_id = context.user_data.get('ua_edit_weapon_attachment_id')
    
    lang = get_user_lang(update, context, db) or 'fa'
    await update.message.reply_text(
        t('common.cancelled', lang),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"ua_admin_review_{attachment_id}" if attachment_id else "ua_admin_pending")
        ]])
    )
    
    context.user_data.pop('ua_edit_weapon_attachment_id', None)
    return ConversationHandler.END
reject_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_reject, pattern="^ua_admin_reject_\\d+$")
    ],
    states={
        UA_ADMIN_REJECT_REASON: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reject_reason)
        ]
    },
    fallbacks=[
        MessageHandler(filters.Regex("^/cancel$"), cancel_reject)
    ],
    name="ua_admin_reject",
    persistent=False,
    per_message=False,
    allow_reentry=True
)

# ConversationHandler برای ویرایش نام سلاح
edit_weapon_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_edit_weapon, pattern="^ua_admin_edit_weapon_\\d+$")
    ],
    states={
        UA_ADMIN_EDIT_WEAPON: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_weapon_name)
        ]
    },
    fallbacks=[
        MessageHandler(filters.Regex("^/cancel$"), cancel_edit_weapon)
    ],
    name="ua_admin_edit_weapon",
    persistent=False,
    per_message=False,
    allow_reentry=True
)


# Export handlers
ua_admin_handlers = [
    CallbackQueryHandler(show_ua_admin_menu, pattern="^ua_admin_menu$"),
    CallbackQueryHandler(show_pending_list, pattern="^ua_admin_pending"),
    CallbackQueryHandler(show_attachment_review, pattern="^ua_admin_review_\\d+$"),
    CallbackQueryHandler(approve_attachment, pattern="^ua_admin_approve_\\d+$"),
    reject_conv_handler,
    edit_weapon_conv_handler,
]
