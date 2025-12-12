"""
Stats Handler - آمار و گزارش‌های سیستم اتچمنت کاربران
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from datetime import datetime, timedelta
from core.database.database_adapter import get_database_adapter
from core.cache.ua_cache_manager import get_ua_cache
from core.security.role_manager import RoleManager, Permission
from utils.logger import get_logger
from utils.i18n import t
from utils.language import get_user_lang
import time

logger = get_logger('ua_stats', 'admin.log')
db = get_database_adapter()
cache = get_ua_cache(db, ttl_seconds=300)  # 5 minutes cache

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


async def show_ua_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش آمار کامل سیستم اتچمنت کاربران"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    try:
        # دریافت آمار از cache (با یک query CTE بهینه)
        start_time = time.time()
        
        # بررسی اگر کاربر refresh خواسته
        force_refresh = 'refresh' in query.data if query.data else False
        
        # دریافت آمار اصلی از cache
        stats = cache.get_stats(force_refresh=force_refresh)
        if not stats:
            logger.error("Failed to get stats from cache")
            await query.answer(t('error.generic', lang), show_alert=True)
            return
        
        # Extract values
        total_attachments = stats.get('total_attachments', 0)
        pending_count = stats.get('pending_count', 0)
        approved_count = stats.get('approved_count', 0)
        rejected_count = stats.get('rejected_count', 0)
        total_users = stats.get('total_users', 0)
        active_users = stats.get('active_users', 0)
        banned_users = stats.get('banned_users', 0)
        br_count = stats.get('br_count', 0)
        mp_count = stats.get('mp_count', 0)
        total_likes = stats.get('total_likes', 0)
        total_reports = stats.get('total_reports', 0)
        pending_reports = stats.get('pending_reports', 0)
        recent_submissions = stats.get('last_week_submissions', 0)
        recent_approvals = stats.get('last_week_approvals', 0)
        
        # نرخ تایید
        approval_rate = 0
        if total_attachments > 0:
            approval_rate = (approved_count / total_attachments) * 100
        
        # دریافت top weapons از cache
        top_weapons = cache.get_top_weapons(limit=10, force_refresh=force_refresh)
        
        # دریافت top users از cache
        top_users = cache.get_top_users(limit=5, force_refresh=force_refresh)
        
        # محاسبه زمان اجرا
        elapsed_time = (time.time() - start_time) * 1000
        logger.info(f"Stats loaded in {elapsed_time:.2f}ms (from {'fresh calculation' if force_refresh else 'cache'})")
        
    except Exception as e:
        logger.error(f"Error fetching UA stats: {e}")
        await query.answer(t('error.generic', lang), show_alert=True)
        return
    
    # ساخت پیام
    message = (
        f"{t('admin.ua.stats.title', lang)}\n\n"
        f"{t('admin.ua.stats.overall.title', lang)}\n"
        f"{t('admin.ua.stats.overall.total', lang, n=total_attachments)}\n"
        f"{t('admin.ua.stats.overall.pending', lang, n=pending_count)}\n"
        f"{t('admin.ua.stats.overall.approved', lang, count=approved_count, rate=f'{approval_rate:.1f}')}\n"
        f"{t('admin.ua.stats.overall.rejected', lang, n=rejected_count)}\n\n"
        f"{t('admin.ua.stats.users.title', lang)}\n"
        f"{t('admin.ua.stats.users.total', lang, n=total_users)}\n"
        f"{t('admin.ua.stats.users.active', lang, n=active_users)}\n"
        f"{t('admin.ua.stats.users.banned', lang, n=banned_users)}\n\n"
        f"{t('admin.ua.stats.modes.title', lang)}\n"
        f"{t('admin.ua.stats.modes.br', lang, n=br_count)}\n"
        f"{t('admin.ua.stats.modes.mp', lang, n=mp_count)}\n\n"
    )
    
    if top_weapons:
        message += t('admin.ua.stats.top_weapons.title', lang) + "\n"
        for i, weapon in enumerate(top_weapons, 1):
            weapon_name = weapon.get('weapon_name', t('common.unknown', lang))
            count = weapon.get('attachment_count', 0)
            message += t('admin.ua.stats.top_weapons.line', lang, i=i, weapon=weapon_name, count=count) + "\n"
        message += "\n"
    
    if top_users:
        message += t('admin.ua.stats.top_users.title', lang) + "\n"
        for i, user in enumerate(top_users, 1):
            user_id = user.get('user_id', 0)
            username = user.get('username')
            count = user.get('approved_count', 0)
            display_name = f"@{username}" if username else f"#{user_id}"
            message += t('admin.ua.stats.top_users.line', lang, i=i, user=display_name, count=count) + "\n"
        message += "\n"
    
    message += (
        f"{t('admin.ua.stats.last7days.title', lang)}\n"
        f"{t('admin.ua.stats.last7days.submissions', lang, n=recent_submissions)}\n"
        f"{t('admin.ua.stats.last7days.approvals', lang, n=recent_approvals)}\n\n"
        f"{t('admin.ua.stats.interaction.title', lang)}\n"
        f"{t('admin.ua.stats.interaction.likes', lang, n=total_likes)}\n"
        f"{t('admin.ua.stats.interaction.reports_total', lang, n=total_reports)}\n"
        f"{t('admin.ua.stats.interaction.reports_pending', lang, n=pending_reports)}"
    )
    
    # نمایش زمان آخرین به‌روزرسانی
    cache_age = ""
    if not force_refresh:
        updated_at = stats.get('updated_at')
        if updated_at:
            try:
                update_time = datetime.fromisoformat(updated_at)
                age_seconds = (datetime.now() - update_time).total_seconds()
                if age_seconds < 60:
                    cache_age = f" ({t('time.seconds_ago', lang, n=int(age_seconds))})"
                else:
                    cache_age = f" ({t('time.minutes_ago', lang, n=int(age_seconds/60))})"
            except Exception as e:
                logger.warning(f"Failed to parse UA stats updated_at '{updated_at}': {e}")
    
    message += "\n_" + t('admin.ua.stats.footer.loaded_in', lang, ms=f"{elapsed_time:.0f}", cache_age=cache_age) + "_"
    
    keyboard = [
        [InlineKeyboardButton(t('admin.ua.stats.buttons.refresh', lang), callback_data="ua_admin_stats_refresh")],
        [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")]
    ]
    
    await query.edit_message_text(
        message,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def show_approved_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست اتچمنت‌های تایید شده"""
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
        # استفاده از cache برای COUNT
        start_time = time.time()
        total = cache.get_paginated_count('approved')
        
        # دریافت لیست (این یکی cache نداره چون pagination داره)
        approved = db.get_user_attachments_by_status('approved', limit=ITEMS_PER_PAGE, offset=page * ITEMS_PER_PAGE)
        
        # Batch load usernames برای جلوگیری از N+1
        if approved:
            user_ids = [att['user_id'] for att in approved]
            users_data = cache.batch_get_users(user_ids)
            for att in approved:
                user_info = users_data.get(att['user_id'], {})
                if not att.get('username'):
                    att['username'] = user_info.get('username', None)
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Approved list loaded in {elapsed:.2f}ms")
    except Exception as e:
        logger.error(f"Error fetching approved attachments: {e}")
        approved = []
        total = 0
    
    if not approved:
        await query.edit_message_text(
            t('admin.ua.approved.empty.title', lang) + "\n\n" + t('admin.ua.approved.empty.desc', lang),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")]])
        )
        return
    
    total_pages = (total - 1) // ITEMS_PER_PAGE + 1
    
    message = (
        t('admin.ua.approved.list.title', lang) + "\n\n" +
        t('admin.ua.approved.list.header', lang, total=total, page=page + 1, total_pages=total_pages) + "\n\n"
    )
    
    keyboard = []
    for att in approved:
        mode_icon = "🎮" if att['mode'] == 'mp' else "🪂"
        username = att.get('username')
        display_user = f"@{username}" if username else t('user.anonymous', lang)
        likes = att.get('like_count', 0)
        
        keyboard.append([
            InlineKeyboardButton(
                f"{mode_icon} {att['attachment_name'][:25]} - {display_user} (💙{likes})",
                callback_data=f"ua_admin_view_approved_{att['id']}"
            )
        ])
    
    # Pagination
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(t('nav.prev', lang), callback_data=f"ua_admin_approved_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(t('nav.next', lang), callback_data=f"ua_admin_approved_page_{page+1}"))
    
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
        # اگه پیام photo بود (از view_approved_attachment برگشته)
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete UA approved list source message: {e}")
        await update.effective_chat.send_message(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def show_rejected_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش لیست اتچمنت‌های رد شده"""
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
        # استفاده از cache برای COUNT
        start_time = time.time()
        total = cache.get_paginated_count('rejected')
        
        # دریافت لیست
        rejected = db.get_user_attachments_by_status('rejected', limit=ITEMS_PER_PAGE, offset=page * ITEMS_PER_PAGE)
        
        # Batch load usernames
        if rejected:
            user_ids = [att['user_id'] for att in rejected]
            users_data = cache.batch_get_users(user_ids)
            for att in rejected:
                user_info = users_data.get(att['user_id'], {})
                if not att.get('username'):
                    att['username'] = user_info.get('username', None)
        
        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Rejected list loaded in {elapsed:.2f}ms")
    except Exception as e:
        logger.error(f"Error fetching rejected attachments: {e}")
        rejected = []
        total = 0
    
    if not rejected:
        await query.edit_message_text(
            t('admin.ua.rejected.empty.title', lang) + "\n\n" + t('admin.ua.rejected.empty.desc', lang),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_menu")]])
        )
        return
    
    total_pages = (total - 1) // ITEMS_PER_PAGE + 1
    
    message = (
        t('admin.ua.rejected.list.title', lang) + "\n\n" +
        t('admin.ua.rejected.list.header', lang, total=total, page=page + 1, total_pages=total_pages) + "\n\n"
    )
    
    keyboard = []
    for att in rejected:
        mode_icon = "🎮" if att['mode'] == 'mp' else "🪂"
        username = att.get('username')
        # Escape markdown characters to prevent parsing errors
        reason = (att.get('rejection_reason') or t('common.no_reason', lang)).replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')[:25]
        name = att['attachment_name'].replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace('`', '\\`')[:20]
        
        keyboard.append([
            InlineKeyboardButton(
                f"{mode_icon} {name} - {reason}",
                callback_data=f"ua_admin_view_rejected_{att['id']}"
            )
        ])
    
    # Pagination
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(t('nav.prev', lang), callback_data=f"ua_admin_rejected_page_{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(t('nav.next', lang), callback_data=f"ua_admin_rejected_page_{page+1}"))
    
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
        # اگه پیام photo بود
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Failed to delete UA rejected list source message: {e}")
        await update.effective_chat.send_message(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def view_approved_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات اتچمنت تایید شده"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    if not has_ua_perm(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return
    
    attachment_id = int(query.data.replace('ua_admin_view_approved_', ''))
    
    # دریافت اتچمنت
    attachment = db.get_user_attachment(attachment_id)
    
    if not attachment:
        await query.answer(t('attachment.not_found', lang), show_alert=True)
        return
    
    # ساخت caption
    from telegram.helpers import escape_markdown
    from config.config import GAME_MODES, WEAPON_CATEGORIES
    
    mode_name = t(f"mode.{attachment['mode']}_short", lang)
    category_name = WEAPON_CATEGORIES.get(attachment['category'], attachment['category'])
    weapon_name = attachment.get('custom_weapon_name', attachment.get('weapon_name', t('common.unknown', lang)))
    username = attachment.get('username') or t('user.anonymous', lang)
    description = attachment.get('description') or t('common.no_description', lang)
    
    # Escape for MarkdownV2
    att_name = escape_markdown(str(attachment['attachment_name']), version=2)
    mode_name_esc = escape_markdown(str(mode_name), version=2)
    weapon_esc = escape_markdown(str(weapon_name), version=2)
    category_esc = escape_markdown(str(category_name), version=2)
    desc_esc = escape_markdown(str(description), version=2)
    
    caption = (
        f"{t('admin.ua.approved.view.title', lang)}\n\n"
        f"{t('admin.ua.approved.view.name', lang)}: {att_name}\n"
        f"{t('admin.ua.approved.view.mode', lang)}: {mode_name_esc}\n"
        f"{t('admin.ua.approved.view.weapon', lang)}: {weapon_esc}\n"
        f"{t('admin.ua.approved.view.category', lang)}: {category_esc}\n"
        f"{t('admin.ua.approved.view.description', lang)}:\n{desc_esc}\n\n"
        f"{t('admin.ua.approved.view.user', lang)}:\n@{username}\n{t('common.id_label', lang)}: {attachment['user_id']}\n"
        f"{t('admin.ua.approved.view.stats', lang)}:\n"
        f"{t('admin.ua.approved.view.views', lang, n=attachment.get('view_count', 0))}\n"
        f"{t('admin.ua.approved.view.likes', lang, n=attachment.get('like_count', 0))}\n"
        f"{t('admin.ua.approved.view.reports', lang, n=attachment.get('report_count', 0))}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_admin_approved")]
    ]
    
    # ارسال تصویر
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete UA approved view source message: {e}")
    
    await update.effective_chat.send_photo(
        photo=attachment['image_file_id'],
        caption=caption,
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# Export handlers
stats_handlers = [
    CallbackQueryHandler(show_ua_stats, pattern="^ua_admin_stats"),  # includes refresh
    CallbackQueryHandler(view_approved_attachment, pattern="^ua_admin_view_approved_\\d+$"),
    CallbackQueryHandler(show_approved_list, pattern="^ua_admin_approved"),
    CallbackQueryHandler(show_rejected_list, pattern="^ua_admin_rejected"),
]
