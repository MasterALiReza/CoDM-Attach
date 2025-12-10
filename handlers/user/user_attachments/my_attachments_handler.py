"""
My Attachments Handler - مدیریت اتچمنت‌های شخصی کاربر
"""

from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from config.config import GAME_MODES, WEAPON_CATEGORIES
from core.database.database_adapter import get_database_adapter
from utils.logger import get_logger
from utils.language import get_user_lang
from utils.i18n import t

logger = get_logger('my_attachments', 'user.log')
db = get_database_adapter()


async def my_attachments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی اتچمنت‌های من"""
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(update, context, db) or 'fa'
    
    user_id = update.effective_user.id
    
    # دریافت آمار کاربر
    stats = db.get_user_submission_stats(user_id)
    
    # دریافت تمام اتچمنت‌های کاربر
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ua.*
                FROM user_attachments ua
                WHERE ua.user_id = %s
                ORDER BY ua.submitted_at DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        all_attachments = [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching user attachments: {e}")
        all_attachments = []
    
    # دسته‌بندی بر اساس وضعیت
    pending = [a for a in all_attachments if a['status'] == 'pending']
    approved = [a for a in all_attachments if a['status'] == 'approved']
    rejected = [a for a in all_attachments if a['status'] == 'rejected']
    
    # پیام آمار
    message = (
        f"{t('ua.my.title', lang)}\n\n"
        f"{t('ua.my.stats_header', lang)}\n"
        f"{t('ua.my.stats.total', lang, n=stats['total_submissions'])}\n"
        f"{t('ua.my.stats.approved', lang, n=stats['approved_submissions'])}\n"
        f"{t('ua.my.stats.rejected', lang, n=stats['rejected_submissions'])}\n"
        f"{t('ua.my.stats.pending', lang, n=len(pending))}\n\n"
    )
    
    if stats['is_banned']:
        message += t('ua.my.status.banned', lang) + "\n"
    elif stats['strike_count'] > 0:
        message += t('ua.my.status.strikes', lang, strike=f"{stats['strike_count']:.1f}") + "\n"
    
    # کیبورد
    keyboard = []
    
    if pending:
        keyboard.append([InlineKeyboardButton(t("ua.my.filter.pending", lang, n=len(pending)), callback_data="ua_my_pending")])
    
    if approved:
        keyboard.append([InlineKeyboardButton(t("ua.my.filter.approved", lang, n=len(approved)), callback_data="ua_my_approved")])
    
    if rejected:
        keyboard.append([InlineKeyboardButton(t("ua.my.filter.rejected", lang, n=len(rejected)), callback_data="ua_my_rejected")])
    
    if not all_attachments:
        message += ("\n" + t('attachment.none', lang))
        keyboard.append([InlineKeyboardButton(t("ua.submit", lang), callback_data="ua_submit")])
    
    keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_menu")])
    
    try:
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        # اگر پیام photo بود، نمیشه edit کرد
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete previous my_attachments menu message: {e}")
        await update.effective_chat.send_message(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_my_attachments_by_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش اتچمنت‌های کاربر بر اساس وضعیت"""
    query = update.callback_query
    await query.answer()
    
    status_map = {
        'ua_my_pending': 'pending',
        'ua_my_approved': 'approved',
        'ua_my_rejected': 'rejected'
    }
    
    status = status_map.get(query.data, 'pending')
    user_id = update.effective_user.id
    
    # دریافت اتچمنت‌ها
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT ua.*
                FROM user_attachments ua
                WHERE ua.user_id = %s AND ua.status = %s
                ORDER BY ua.submitted_at DESC
                """,
                (user_id, status),
            )
            rows = cursor.fetchall()
        attachments = [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching attachments: {e}")
        attachments = []
    
    # عنوان بر اساس وضعیت
    status_titles = {
        'pending': t('ua.my.status_title.pending', lang),
        'approved': t('ua.my.status_title.approved', lang),
        'rejected': t('ua.my.status_title.rejected', lang)
    }
    
    message = f"📁 {status_titles[status]}\n\n"
    
    lang = get_user_lang(update, context, db) or 'fa'
    if not attachments:
        message += t('attachment.none', lang)
        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_my")]]
    else:
        message += t('ua.my.count', lang, n=len(attachments)) + "\n\n"
        
        keyboard = []
        for att in attachments[:20]:  # حداکثر 20 تا
            mode_icon = "🎮" if att['mode'] == 'mp' else "🪂"
            weapon = att.get('custom_weapon_name', t('common.unknown', lang))
            btn_text = f"{mode_icon} {att['attachment_name'][:25]} - {weapon}"
            callback_data = f"ua_my_detail_{att['id']}"
            
            keyboard.append([
                InlineKeyboardButton(btn_text, callback_data=callback_data)
            ])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_my")])
    
    try:
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        # اگر پیام photo بود، نمیشه edit کرد
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete previous my_attachments status message: {e}")
        await update.effective_chat.send_message(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_my_attachment_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات اتچمنت شخصی"""
    query = update.callback_query
    await query.answer()
    
    attachment_id = int(query.data.replace('ua_my_detail_', ''))
    
    # دریافت اتچمنت
    attachment = db.get_user_attachment(attachment_id)
    
    if not attachment:
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('attachment.not_found', lang), show_alert=True)
        return
    
    if attachment['user_id'] != update.effective_user.id:
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    # ساخت پیام
    from telegram.helpers import escape_markdown
    
    lang = get_user_lang(update, context, db) or 'fa'
    mode_name = t(f"mode.{attachment['mode']}_short", lang)
    status_icons = {
        'pending': '⏳',
        'approved': '✅',
        'rejected': '❌'
    }
    
    status_icon = status_icons.get(attachment['status'], '❓')
    description = attachment.get('description') or t('common.no_description', lang)
    
    # دریافت نام دسته از کلید
    category_key = attachment.get('category', attachment.get('category_name', ''))
    category_persian = t(f"category.{category_key}", lang)
    
    # Escape for MarkdownV2
    att_name = escape_markdown(str(attachment['attachment_name']), version=2)
    status_text = escape_markdown(str(attachment['status'].upper()), version=2)
    mode_name_esc = escape_markdown(str(mode_name), version=2)
    weapon_raw = attachment.get('custom_weapon_name', attachment.get('weapon_name', t('common.unknown', lang)))
    weapon_name = escape_markdown(str(weapon_raw), version=2)
    category_name_esc = escape_markdown(str(category_persian), version=2)
    description_esc = escape_markdown(str(description), version=2)
    # Format submitted_at safely
    sub_at = attachment.get('submitted_at')
    if isinstance(sub_at, datetime):
        sub_ts = sub_at.date().isoformat()
    elif isinstance(sub_at, date):
        sub_ts = sub_at.isoformat()
    elif isinstance(sub_at, str):
        sub_ts = sub_at[:10]
    else:
        sub_ts = 'نامشخص'
    date_str = escape_markdown(sub_ts, version=2)
    
    caption = (
        f"📎 *{att_name}*\n\n"
        f"{status_icon} *وضعیت:* {status_text}\n"
        f"🎮 {t('mode.label', lang)}: {mode_name_esc}\n"
        f"🔫 {t('weapon.label', lang)}: {weapon_name}\n"
        f"📂 {t('category.label', lang)}: {category_name_esc}\n\n"
        f"💬 توضیحات:\n{description_esc}\n\n"
        f"📅 تاریخ ارسال: {date_str}\n"
    )
    
    # اطلاعات اضافی بر اساس وضعیت
    if attachment['status'] == 'approved':
        # Format approved_at safely
        appr_at = attachment.get('approved_at')
        if isinstance(appr_at, datetime):
            appr_ts = appr_at.date().isoformat()
        elif isinstance(appr_at, date):
            appr_ts = appr_at.isoformat()
        elif isinstance(appr_at, str):
            appr_ts = appr_at[:10]
        else:
            appr_ts = 'نامشخص'
        approved_date = escape_markdown(appr_ts, version=2)
        caption += (
            f"✅ {escape_markdown(t('ua.approved_at', lang), version=2)}: {approved_date}\n"
            f"👁 {escape_markdown(t('ua.views', lang), version=2)}: {attachment.get('view_count', 0)}\n"
            f"👍 {escape_markdown(t('ua.likes', lang), version=2)}: {attachment.get('like_count', 0)}\n"
        )
    elif attachment['status'] == 'rejected':
        reason = escape_markdown(str(attachment.get('rejection_reason', t('common.no_description', lang))), version=2)
        caption += f"\n❌ {escape_markdown(t('ua.rejected.reason', lang), version=2)}\n{reason}\n"
    elif attachment['status'] == 'pending':
        caption += "\n" + escape_markdown(t('ua.pending.review', lang), version=2)
    
    # کیبورد
    keyboard = []
    
    if attachment['status'] == 'pending':
        keyboard.append([InlineKeyboardButton(t("menu.buttons.delete", lang), callback_data=f"ua_my_delete_{attachment_id}")])
    
    keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"ua_my_{attachment['status']}")])
    
    # ارسال تصویر
    try:
        await update.effective_chat.send_photo(
            photo=attachment['image_file_id'],
            caption=caption,
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"Error sending photo for attachment {attachment_id}: {e}")
        await query.answer(t('ua.error.view_image', lang), show_alert=True)
        return
    
    # حذف پیام قبلی
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete previous my_attachments detail message: {e}")


async def delete_my_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف اتچمنت شخصی (فقط pending)"""
    query = update.callback_query
    
    attachment_id = int(query.data.replace('ua_my_delete_', ''))
    user_id = update.effective_user.id
    
    # بررسی مالکیت و وضعیت
    attachment = db.get_user_attachment(attachment_id)
    
    if not attachment or attachment['user_id'] != user_id:
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    if attachment['status'] != 'pending':
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('ua.error.delete_only_pending', lang), show_alert=True)
        return
    
    # حذف
    try:
        with db.transaction() as tconn:
            cur = tconn.cursor()
            cur.execute("DELETE FROM user_attachments WHERE id = %s", (attachment_id,))
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('ua.success.deleted', lang), show_alert=True)
        
        # حذف تصویر و بازگشت
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete my_attachments message after delete: {e}")
        
        # نمایش لیست pending
        context.user_data['temp_callback_data'] = 'ua_my_pending'
        await show_my_attachments_by_status(update, context)
        
    except Exception as e:
        logger.error(f"Error deleting attachment: {e}")
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('error.generic', lang), show_alert=True)


async def back_from_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت از جزئیات"""
    query = update.callback_query
    await query.answer()
    
    # حذف تصویر
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete my_attachments image message on back: {e}")
    
    # استفاده از callback ذخیره شده
    callback_data = context.user_data.get('temp_callback_data', 'ua_my')
    context.user_data['query_data'] = callback_data
    
    if callback_data == 'ua_my':
        await my_attachments_menu(update, context)
    else:
        await show_my_attachments_by_status(update, context)


# Export handlers
my_attachments_handlers = [
    CallbackQueryHandler(show_my_attachment_detail, pattern="^ua_my_detail_\\d+$"),
    CallbackQueryHandler(delete_my_attachment, pattern="^ua_my_delete_\\d+$"),
    CallbackQueryHandler(show_my_attachments_by_status, pattern="^ua_my_(pending|approved|rejected)$"),
    CallbackQueryHandler(my_attachments_menu, pattern="^ua_my$"),
]
