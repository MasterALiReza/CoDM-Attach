"""
Reports Handler - مدیریت گزارش‌های کاربران
"""

from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from config.config import GAME_MODES
from core.database.database_adapter import get_database_adapter
from core.security.role_manager import RoleManager, Permission
from utils.logger import get_logger
from psycopg.rows import dict_row
from telegram.helpers import escape_markdown
from core.cache.ua_cache_manager import get_ua_cache
from utils.i18n import t
from utils.language import get_user_lang

logger = get_logger('ua_reports', 'admin.log')
db = get_database_adapter()
cache = get_ua_cache(db, ttl_seconds=300)

# RBAC helper
role_manager = RoleManager(db)

def has_ua_perm(user_id: int) -> bool:
    """Check if user can manage user attachments (UA)."""
    try:
        if role_manager.is_super_admin(user_id):
            return True
        return role_manager.has_permission(user_id, Permission.MANAGE_USER_ATTACHMENTS)
    except Exception:
        return db.is_admin(user_id)


async def show_reports_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست گزارش‌های pending"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    # دریافت صفحه
    page = 0
    if 'page_' in query.data:
        page = int(query.data.split('_')[-1])
    
    ITEMS_PER_PAGE = 10
    
    try:
        from psycopg import sql  # optional
        with db.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            # تلاش برای اسکیما جدید (reporter_id/reported_at) و در صورت خطا fallback به اسکیما قدیمی (user_id/created_at)
            try:
                cursor.execute(
                    """
                    SELECT 
                        r.id,
                        r.attachment_id,
                        r.reporter_id,
                        r.reason,
                        r.reported_at,
                        ua.attachment_name,
                        ua.mode,
                        reporter.username as reporter_username,
                        owner.username as owner_username
                    FROM user_attachment_reports r
                    JOIN user_attachments ua ON r.attachment_id = ua.id
                    JOIN users reporter ON r.reporter_id = reporter.user_id
                    JOIN users owner ON ua.user_id = owner.user_id
                    WHERE r.status = 'pending'
                    ORDER BY r.reported_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (ITEMS_PER_PAGE, page * ITEMS_PER_PAGE),
                )
            except Exception:
                cursor.execute(
                    """
                    SELECT 
                        r.id,
                        r.attachment_id,
                        r.user_id as reporter_id,
                        r.reason,
                        r.created_at as reported_at,
                        ua.attachment_name,
                        ua.mode,
                        reporter.username as reporter_username,
                        owner.username as owner_username
                    FROM user_attachment_reports r
                    JOIN user_attachments ua ON r.attachment_id = ua.id
                    JOIN users reporter ON r.user_id = reporter.user_id
                    JOIN users owner ON ua.user_id = owner.user_id
                    WHERE r.status = 'pending'
                    ORDER BY r.created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (ITEMS_PER_PAGE, page * ITEMS_PER_PAGE),
                )
            reports = cursor.fetchall()

            cursor.execute(
                """
                SELECT COUNT(*) AS cnt FROM user_attachment_reports WHERE status = 'pending'
                """
            )
            total_row = cursor.fetchone()
            total = int((total_row or {}).get('cnt') or 0)
            cursor.close()
    except Exception as e:
        logger.error(f"Error fetching reports: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)
        return
    
    if not reports:
        try:
            await query.edit_message_text(
                t('admin.ua.reports.empty.title', lang) + "\n\n" + t('admin.ua.reports.empty.desc', lang),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")]])
            )
        except Exception:
            try:
                await query.message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete UA reports empty message: {e}")
            await query.message.reply_text(
                t('admin.ua.reports.empty.title', lang) + "\n\n" + t('admin.ua.reports.empty.desc', lang),
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")]])
            )
        return
    
    total_pages = (total - 1) // ITEMS_PER_PAGE + 1
    
    message = (
        t('admin.ua.reports.list.title', lang) + "\n\n" +
        t('admin.ua.reports.list.header', lang, total=total, page=page + 1, total_pages=total_pages) + "\n\n"
    )
    
    keyboard = []
    for report in reports:
        report_id = report.get('id')
        att_id = report.get('attachment_id')
        reporter_id = report.get('reporter_id')
        reason = report.get('reason')
        reported_at = report.get('reported_at')
        att_name = report.get('attachment_name')
        mode = report.get('mode')
        reporter_username = report.get('reporter_username')
        owner_username = report.get('owner_username')
        
        mode_icon = "🎮" if mode == 'mp' else "🪂"
        reporter_name = f"@{reporter_username}" if reporter_username else t('user.anonymous', lang)
        reason_short = (reason[:20] + "...") if len(reason) > 20 else reason
        
        keyboard.append([
            InlineKeyboardButton(
                f"{mode_icon} {att_name[:20]} - {reason_short}",
                callback_data=f"ua_admin_report_{report_id}"
            )
        ])
    
    # Pagination
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(t('nav.prev', lang), callback_data=f"ua_admin_reports_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(t('nav.next', lang), callback_data=f"ua_admin_reports_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")])
    
    try:
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete UA reports list source message: {e}")
        await query.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_report_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات گزارش"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    report_id = int(query.data.replace('ua_admin_report_', ''))
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            try:
                cursor.execute(
                    """
                    SELECT 
                        r.id,
                        r.attachment_id,
                        r.reporter_id,
                        r.reason,
                        r.reported_at,
                        ua.attachment_name,
                        ua.description,
                        ua.mode,
                        ua.image_file_id,
                        ua.user_id as owner_id,
                        ua.like_count,
                        reporter.username as reporter_username,
                        reporter.first_name as reporter_first_name,
                        owner.username as owner_username,
                        owner.first_name as owner_first_name,
                        w.name as weapon_name,
                        wc.name as category_name
                    FROM user_attachment_reports r
                    JOIN user_attachments ua ON r.attachment_id = ua.id
                    JOIN users reporter ON r.reporter_id = reporter.user_id
                    JOIN users owner ON ua.user_id = owner.user_id
                    JOIN weapons w ON ua.weapon_id = w.id
                    JOIN weapon_categories wc ON w.category_id = wc.id
                    WHERE r.id = %s
                    """,
                    (report_id,),
                )
            except Exception:
                cursor.execute(
                    """
                    SELECT 
                        r.id,
                        r.attachment_id,
                        r.user_id as reporter_id,
                        r.reason,
                        r.created_at as reported_at,
                        ua.attachment_name,
                        ua.description,
                        ua.mode,
                        ua.image_file_id,
                        ua.user_id as owner_id,
                        ua.like_count,
                        reporter.username as reporter_username,
                        reporter.first_name as reporter_first_name,
                        owner.username as owner_username,
                        owner.first_name as owner_first_name,
                        w.name as weapon_name,
                        wc.name as category_name
                    FROM user_attachment_reports r
                    JOIN user_attachments ua ON r.attachment_id = ua.id
                    JOIN users reporter ON r.user_id = reporter.user_id
                    JOIN users owner ON ua.user_id = owner.user_id
                    JOIN weapons w ON ua.weapon_id = w.id
                    JOIN weapon_categories wc ON w.category_id = wc.id
                    WHERE r.id = %s
                    """,
                    (report_id,),
                )
            report_data = cursor.fetchone()
            cursor.close()

        if not report_data:
            await query.answer(t('admin.ua.reports.not_found', lang), show_alert=True)
            return
        
    except Exception as e:
        logger.error(f"Error fetching report detail: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)
        return
    
    rep_id = report_data.get('id')
    att_id = report_data.get('attachment_id')
    reporter_id = report_data.get('reporter_id')
    reason = report_data.get('reason')
    reported_at = report_data.get('reported_at')
    att_name = report_data.get('attachment_name')
    description = report_data.get('description')
    mode = report_data.get('mode')
    image_file_id = report_data.get('image_file_id')
    owner_id = report_data.get('owner_id')
    like_count = report_data.get('like_count')
    reporter_username = report_data.get('reporter_username')
    reporter_first_name = report_data.get('reporter_first_name')
    owner_username = report_data.get('owner_username')
    owner_first_name = report_data.get('owner_first_name')
    weapon_name = report_data.get('weapon_name')
    category_name = report_data.get('category_name')
    
    mode_name = t(f"mode.{mode}_short", lang)
    reporter_name = f"@{reporter_username}" if reporter_username else (reporter_first_name or t('user.anonymous', lang))
    owner_name = f"@{owner_username}" if owner_username else (owner_first_name or t('user.anonymous', lang))
    
    # Safe date formatting
    if isinstance(reported_at, datetime):
        reported_date = reported_at.date().isoformat()
    elif isinstance(reported_at, date):
        reported_date = reported_at.isoformat()
    else:
        reported_date = str(reported_at)[:10]
    
    # Escape dynamic fields for MarkdownV2 (after computing reported_date)
    s_att_name = escape_markdown(att_name or "", version=2)
    s_mode_name = escape_markdown(mode_name or "", version=2)
    s_weapon_name = escape_markdown(weapon_name or "", version=2)
    s_category_name = escape_markdown(category_name or "", version=2)
    s_description = escape_markdown((description or t('common.no_description', lang)), version=2)
    s_reason = escape_markdown(reason or "", version=2)
    s_reporter_name = escape_markdown(reporter_name or t('user.anonymous', lang), version=2)
    s_owner_name = escape_markdown(owner_name or t('user.anonymous', lang), version=2)
    s_reported_date = escape_markdown(reported_date or "", version=2)
    
    caption = (
        f"{t('admin.ua.reports.detail.title', lang)}\n\n"
        f"{t('admin.ua.reports.detail.attachment', lang)}: {s_att_name}\n"
        f"{t('admin.ua.reports.detail.mode', lang)}: {s_mode_name}\n"
        f"{t('admin.ua.reports.detail.weapon', lang)}: {s_weapon_name}\n"
        f"{t('admin.ua.reports.detail.category', lang)}: {s_category_name}\n"
        f"{t('admin.ua.reports.detail.likes', lang, n=like_count)}\n"
        f"{t('admin.ua.reports.detail.description', lang)}: {s_description}\n\n"
        f"{t('admin.ua.reports.detail.reason', lang)}\\n{s_reason}\\n\\n"
        f"{t('admin.ua.reports.detail.reporter_label', lang)}: {s_reporter_name} \\\\({t('common.id_label', lang)}: {reporter_id}\\\\)\\n"
        f"{t('admin.ua.reports.detail.owner_label', lang)}: {s_owner_name} \\\\({t('common.id_label', lang)}: {owner_id}\\\\)\\n"
        f"{t('admin.ua.reports.detail.date_label', lang)}: {s_reported_date}"
    )
    
    keyboard = [
        [
            InlineKeyboardButton(t('admin.ua.reports.buttons.delete_attachment', lang), callback_data=f"ua_admin_report_delete_{att_id}_{rep_id}"),
            InlineKeyboardButton(t('admin.ua.reports.buttons.warn_owner', lang), callback_data=f"ua_admin_report_warn_{owner_id}_{rep_id}")
        ],
        [InlineKeyboardButton(t('admin.ua.reports.buttons.dismiss', lang), callback_data=f"ua_admin_report_dismiss_{rep_id}")],
        [InlineKeyboardButton(t('admin.ua.reports.buttons.back_to_list', lang), callback_data="ua_admin_reports")]
    ]
    
    # ارسال تصویر یا متن در صورت نبود تصویر
    sent_ok = False
    if image_file_id:
        try:
            await query.message.reply_photo(
                photo=image_file_id,
                caption=caption,
                parse_mode='MarkdownV2',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            sent_ok = True
        except Exception:
            sent_ok = False
    if not sent_ok:
        await query.message.reply_text(
            text=caption,
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    # حذف پیام قبلی
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete UA report detail source message: {e}")


async def delete_reported_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف اتچمنت گزارش شده"""
    query = update.callback_query
    lang = get_user_lang(update, context, db) or 'fa'
    
    admin_id = update.effective_user.id
    if not has_ua_perm(admin_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    parts = query.data.replace('ua_admin_report_delete_', '').split('_')
    att_id = int(parts[0])
    report_id = int(parts[1])
    
    try:
        with db.transaction() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            # دریافت اطلاعات اتچمنت و گزارش
            cursor.execute(
                """
                SELECT ua.user_id, ua.attachment_name, u.username, u.first_name
                FROM user_attachments ua
                JOIN users u ON ua.user_id = u.user_id
                WHERE ua.id = %s
                """,
                (att_id,),
            )
            att_info = cursor.fetchone()
            if not att_info:
                cursor.close()
                await query.answer(t('attachment.not_found', lang), show_alert=True)
                return

            owner_id = att_info.get('user_id')
            att_name = att_info.get('attachment_name')
            username = att_info.get('username')
            first_name = att_info.get('first_name')

            # حذف اتچمنت
            cursor.execute("DELETE FROM user_attachments WHERE id = %s", (att_id,))

            # به‌روزرسانی وضعیت گزارش (PostgreSQL timestamp)
            cursor.execute(
                """
                UPDATE user_attachment_reports 
                SET status = 'resolved', resolved_by = %s, resolved_at = NOW()
                WHERE id = %s
                """,
                (admin_id, report_id),
            )
            cursor.close()
        
        # invalidate stats cache to refresh counts in admin menu
        try:
            cache.invalidate('stats')
            cache.invalidate('count_')
        except Exception:
            pass

        # اخطار به صاحب اتچمنت
        strike_value = 0.5
        db.update_submission_stats(owner_id, add_violation=1, add_strike=strike_value)
        
        # بررسی ban
        stats = db.get_user_submission_stats(owner_id)
        if stats['strike_count'] >= 3.0 and not stats['is_banned']:
            db.ban_user_from_submissions(
                owner_id,
                t('admin.ua.reports.auto_ban.reason', lang, count=f"{stats['strike_count']:.1f}"),
                banned_by=admin_id
            )
            ban_message = "\n\n" + t('admin.ua.reports.auto_ban.note', lang)
        else:
            ban_message = ""
        
        try:
            safe_att_name = escape_markdown(att_name or "", version=2)
            s_strike_value = escape_markdown(f"{strike_value:.1f}", version=2)
            s_strike_count = escape_markdown(f"{stats['strike_count']:.1f}", version=2)
            s_limit = escape_markdown("3.0", version=2)
            notif_text = t('user.ua.report.deleted', lang, name=safe_att_name, strike_value=s_strike_value, strike_count=s_strike_count, limit=s_limit)
            if ban_message:
                notif_text += escape_markdown(ban_message, version=2)
            await context.bot.send_message(
                chat_id=owner_id,
                text=notif_text,
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logger.error(f"Error sending deletion notification: {e}")
        
        await query.answer(t('admin.ua.reports.delete.success', lang, strike=f"{strike_value}"), show_alert=True)
        
        # بازگشت به لیست
        await show_reports_list(update, context)
        
    except Exception as e:
        logger.error(f"Error deleting reported attachment: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)


async def warn_owner_about_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    admin_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(admin_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    parts = query.data.replace('ua_admin_report_warn_', '').split('_')
    try:
        owner_id = int(parts[0])
        report_id = int(parts[1])
    except Exception:
        await query.answer(t('error.generic', lang), show_alert=True)
        return
    
    try:
        with db.transaction() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            # دریافت اطلاعات لازم برای پیام
            cursor.execute(
                """
                SELECT ua.attachment_name, u.username, u.first_name
                FROM user_attachment_reports r
                JOIN user_attachments ua ON r.attachment_id = ua.id
                JOIN users u ON ua.user_id = u.user_id
                WHERE r.id = %s
                """,
                (report_id,),
            )
            row = cursor.fetchone()
            att_name = (row or {}).get('attachment_name') or ""
            username = (row or {}).get('username')
            first_name = (row or {}).get('first_name')
            
            # بروزرسانی وضعیت گزارش
            cursor.execute(
                """
                UPDATE user_attachment_reports 
                SET status = 'resolved', resolved_by = %s, resolved_at = NOW()
                WHERE id = %s
                """,
                (admin_id, report_id),
            )
            cursor.close()
        
        # invalidate stats cache to refresh counts immediately
        try:
            cache.invalidate('stats')
            cache.invalidate('count_')
        except Exception:
            pass

        # ثبت اخطار
        strike_value = 0.5
        db.update_submission_stats(owner_id, add_violation=1, add_strike=strike_value)
        stats = db.get_user_submission_stats(owner_id)
        if stats['strike_count'] >= 3.0 and not stats['is_banned']:
            db.ban_user_from_submissions(
                owner_id,
                t('admin.ua.reports.auto_ban.reason', lang, count=f"{stats['strike_count']:.1f}")
            )
            ban_message = "\n\n" + t('admin.ua.reports.auto_ban.note', lang)
        else:
            ban_message = ""
        
        # ارسال پیام به صاحب
        try:
            safe_att_name = escape_markdown(att_name or "", version=2)
            s_strike_value = escape_markdown(f"{strike_value:.1f}", version=2)
            s_strike_count = escape_markdown(f"{stats['strike_count']:.1f}", version=2)
            s_limit = escape_markdown("3.0", version=2)
            notif_text = t('user.ua.report.warn', lang, name=safe_att_name, strike_value=s_strike_value, strike_count=s_strike_count, limit=s_limit)
            if ban_message:
                notif_text += escape_markdown(ban_message, version=2)
            await context.bot.send_message(
                chat_id=owner_id,
                text=notif_text,
                parse_mode='MarkdownV2'
            )
        except Exception as e:
            logger.error(f"Error sending warn notification: {e}")
        
        await query.answer(t('admin.ua.reports.warn.success', lang), show_alert=True)
        # بازگشت به لیست
        await show_reports_list(update, context)
    
    except Exception as e:
        logger.error(f"Error warning owner about report: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)


async def dismiss_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رد کردن گزارش (بدون اقدام)"""
    query = update.callback_query
    
    admin_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(admin_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    report_id = int(query.data.replace('ua_admin_report_dismiss_', ''))
    
    try:
        with db.transaction() as conn:
            cursor = conn.cursor(row_factory=dict_row)
            cursor.execute(
                """
                UPDATE user_attachment_reports 
                SET status = 'dismissed', resolved_by = %s, resolved_at = NOW()
                WHERE id = %s
                """,
                (admin_id, report_id),
            )
            cursor.close()
        
        # invalidate stats cache so pending_reports count updates
        try:
            cache.invalidate('stats')
            cache.invalidate('count_')
        except Exception:
            pass

        await query.answer(t('admin.ua.reports.dismiss.success', lang), show_alert=True)
        
        # بازگشت به لیست
        await show_reports_list(update, context)
        
    except Exception as e:
        logger.error(f"Error dismissing report: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)


# Export handlers
reports_handlers = [
    CallbackQueryHandler(show_reports_list, pattern="^ua_admin_reports"),
    CallbackQueryHandler(show_report_detail, pattern="^ua_admin_report_\\d+$"),
    CallbackQueryHandler(delete_reported_attachment, pattern="^ua_admin_report_delete_"),
    CallbackQueryHandler(warn_owner_about_report, pattern="^ua_admin_report_warn_"),
    CallbackQueryHandler(dismiss_report, pattern="^ua_admin_report_dismiss_"),
]
