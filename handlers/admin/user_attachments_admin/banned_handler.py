"""
Banned Users Handler - مدیریت کاربران محروم
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from core.database.database_adapter import get_database_adapter
from core.security.role_manager import RoleManager, Permission
from utils.logger import get_logger
from utils.i18n import t
from utils.language import get_user_lang

logger = get_logger('ua_banned', 'admin.log')
db = get_database_adapter()

# RBAC helper
role_manager = RoleManager(db)

# Conversation state for ban reason
UA_ADMIN_BAN_REASON = 1

def has_ua_perm(user_id: int) -> bool:
    """Check if user can manage user attachments (UA)."""
    try:
        if role_manager.is_super_admin(user_id):
            return True
        return role_manager.has_permission(user_id, Permission.MANAGE_USER_ATTACHMENTS)
    except Exception:
        return db.is_admin(user_id)


async def show_banned_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست کاربران محروم"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT 
                uss.user_id,
                u.username,
                u.first_name,
                uss.banned_reason,
                uss.banned_at,
                uss.total_submissions,
                uss.approved_submissions,
                uss.rejected_submissions,
                uss.strike_count
            FROM user_submission_stats uss
            JOIN users u ON uss.user_id = u.user_id
            WHERE uss.is_banned = TRUE
            ORDER BY uss.banned_at DESC
        """)
            banned_users = cursor.fetchall()
    except Exception as e:
        logger.error(f"Error fetching banned users: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)
        return
    
    if not banned_users:
        await query.edit_message_text(
            t('admin.ua.banned.empty.title', lang) + "\n\n" + t('admin.ua.banned.empty.desc', lang),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")]])
        )
        return
    
    message = t('admin.ua.banned.list.title', lang, n=len(banned_users)) + "\n\n"
    
    keyboard = []
    for user_data in banned_users:
        (uid, username, first_name, reason, banned_at, total, approved, rejected, strikes) = user_data
        
        display_name = f"@{username}" if username else (first_name or t('user.anonymous', lang))
        reason_short = (reason[:25] + "...") if reason and len(reason) > 25 else (reason or t('common.no_reason', lang))
        
        keyboard.append([
            InlineKeyboardButton(
                f"🚫 {display_name} - {reason_short}",
                callback_data=f"ua_admin_banned_detail_{uid}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")])
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_banned_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات کاربر محروم"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    banned_user_id = int(query.data.replace('ua_admin_banned_detail_', ''))
    
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT 
                uss.user_id,
                u.username,
                u.first_name,
                uss.banned_reason,
                uss.banned_at,
                uss.total_submissions,
                uss.approved_submissions,
                uss.rejected_submissions,
                uss.strike_count
            FROM user_submission_stats uss
            JOIN users u ON uss.user_id = u.user_id
            WHERE uss.user_id = %s AND uss.is_banned = TRUE
        """, (banned_user_id,))
            user_info = cursor.fetchone()
        
        if not user_info:
            await query.answer(t('admin.ua.banned.not_found', lang), show_alert=True)
            return
        
        (uid, username, first_name, reason, banned_at, total, approved, rejected, strikes) = user_info
        
    except Exception as e:
        logger.error(f"Error fetching banned user detail: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)
        return
    
    display_name = f"@{username}" if username else (first_name or t('user.anonymous', lang))
    # تاریخ محرومیت سازگار با هر دو نوع str/datetime
    banned_at_display = t('common.unknown', lang)
    if banned_at:
        if isinstance(banned_at, str):
            banned_at_display = banned_at[:10]
        else:
            try:
                banned_at_display = banned_at.strftime('%Y-%m-%d')
            except Exception:
                banned_at_display = str(banned_at)[:10]
    
    message = (
        f"{t('admin.ua.banned.detail.title', lang)}\n\n"
        f"{t('admin.ua.banned.detail.user_label', lang)}: {display_name}\n"
        f"{t('admin.ua.banned.detail.id_label', lang)}: `{uid}`\n\n"
        f"{t('admin.ua.banned.detail.reason_label', lang)}:\n{reason or t('common.no_reason', lang)}\n\n"
        f"{t('admin.ua.banned.detail.banned_at_label', lang)}: {banned_at_display}\n\n"
        f"{t('admin.ua.banned.detail.stats_title', lang)}:\n"
        f"{t('admin.ua.banned.detail.stats.total', lang, n=total)}\n"
        f"{t('admin.ua.banned.detail.stats.approved', lang, n=approved)}\n"
        f"{t('admin.ua.banned.detail.stats.rejected', lang, n=rejected)}\n"
        f"{t('admin.ua.banned.detail.stats.strikes', lang, strikes=f'{strikes:.1f}')}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(t('admin.ua.banned.buttons.unban', lang), callback_data=f"ua_admin_unban_{uid}")],
        [InlineKeyboardButton(t('admin.ua.banned.buttons.back_to_list', lang), callback_data="ua_admin_banned")]
    ]
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """رفع محرومیت کاربر"""
    query = update.callback_query
    
    admin_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(admin_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    banned_user_id = int(query.data.replace('ua_admin_unban_', ''))
    
    try:
        # رفع محرومیت
        success = db.unban_user_from_attachments(banned_user_id)
        
        if success:
            # دریافت اطلاعات کاربر برای notification
            user_info = db.get_user(banned_user_id)
            
            # Notification به کاربر
            try:
                notif_text = t('user.ua.unbanned', lang)
                await context.bot.send_message(
                    chat_id=banned_user_id,
                    text=notif_text,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error sending unban notification: {e}")
            
            await query.answer(t('admin.ua.banned.unban.success', lang), show_alert=True)
            
            # بازگشت به لیست
            await show_banned_users(update, context)
        else:
            await query.answer(t('admin.ua.banned.unban.error', lang), show_alert=True)
            
    except Exception as e:
        logger.error(f"Error unbanning user: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)


async def ban_user_from_review(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """محروم کردن کاربر از صفحه review"""
    query = update.callback_query
    await query.answer()
    
    admin_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(admin_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    target_user_id = int(query.data.replace('ua_admin_ban_', ''))
    
    # درخواست دلیل
    await query.edit_message_caption(
        caption=(
            query.message.caption + "\n\n" +
            t('admin.ua.banned.ban_request.title', lang) + "\n\n" +
            t('admin.ua.banned.ban_request.prompt', lang) + "\n" +
            t('admin.ua.banned.ban_request.limit', lang) + "\n\n" +
            t('admin.ua.banned.ban_request.hint_cancel', lang)
        ),
        parse_mode='Markdown'
    )
    
    # ذخیره user_id برای استفاده در handler بعدی
    context.user_data['ua_ban_user_id'] = target_user_id
    
    # پاک کردن ReplyKeyboard کاربر تا متن به همین مکالمه برسد
    try:
        await query.message.reply_text(t('admin.ua.banned.ban_request.type_reason', lang), reply_markup=ReplyKeyboardRemove())
    except Exception:
        pass

    return UA_ADMIN_BAN_REASON


async def receive_ban_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    lang = get_user_lang(update, context, db) or 'fa'
    if len(reason) > 200:
        await update.message.reply_text(t('admin.ua.banned.ban_request.too_long', lang))
        return UA_ADMIN_BAN_REASON
    
    target_user_id = context.user_data.get('ua_ban_user_id')
    admin_id = update.effective_user.id
    if not target_user_id:
        await update.message.reply_text(t('error.generic', lang))
        return ConversationHandler.END
    
    success = db.ban_user_from_submissions(target_user_id, reason, banned_by=admin_id)
    if success:
        try:
            notif_text = t('user.ua.banned', lang, reason=reason)
            await context.bot.send_message(
                chat_id=target_user_id,
                text=notif_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Error sending ban notification: {e}")
        await update.message.reply_text(
            t('admin.ua.banned.ban.success', lang),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_banned")]])
        )
    else:
        await update.message.reply_text(t('admin.ua.banned.ban.error', lang))
    
    context.user_data.pop('ua_ban_user_id', None)
    return ConversationHandler.END


async def cancel_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_lang(update, context, db) or 'fa'
    await update.message.reply_text(
        t('common.cancelled', lang),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_banned")]])
    )
    context.user_data.pop('ua_ban_user_id', None)
    return ConversationHandler.END


# Export handlers
ban_user_conv_handler = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(ban_user_from_review, pattern="^ua_admin_ban_\\d+$")
    ],
    states={
        UA_ADMIN_BAN_REASON: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_reason)
        ]
    },
    fallbacks=[
        MessageHandler(filters.Regex("^/cancel$"), cancel_ban)
    ],
    name="ua_admin_ban",
    persistent=False,
    per_message=False,
    allow_reentry=True
)

banned_handlers = [
    CallbackQueryHandler(show_banned_users, pattern="^ua_admin_banned$"),
    CallbackQueryHandler(show_banned_detail, pattern="^ua_admin_banned_detail_\\d+$"),
    CallbackQueryHandler(unban_user, pattern="^ua_admin_unban_\\d+$"),
    ban_user_conv_handler,
]
