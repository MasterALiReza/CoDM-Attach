"""
Browse Handler - نمایش اتچمنت‌های تایید شده کاربران
"""

import json
from datetime import datetime, date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from config.config import WEAPON_CATEGORIES, WEAPON_CATEGORIES_SHORT, GAME_MODES, build_category_keyboard
from core.database.database_adapter import get_database_adapter
from core.cache.ua_cache_manager import get_ua_cache
from utils.logger import get_logger
from utils.language import get_user_lang
from utils.i18n import t

logger = get_logger('browse_attachments', 'user.log')
db = get_database_adapter()
cache = get_ua_cache(db, ttl_seconds=300)

# تعداد اتچمنت در هر صفحه
ATTACHMENTS_PER_PAGE = 5


async def browse_attachments_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی اصلی Browse"""
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(update, context, db) or 'fa'
    
    # دریافت مودهای فعال
    enabled_modes_str = db.get_ua_setting('enabled_modes') or '["mp","br"]'
    enabled_modes = json.loads(enabled_modes_str)
    
    keyboard = []
    mode_buttons = []
    
    # ترتیب: BR راست، MP چپ
    if 'br' in enabled_modes:
        mode_buttons.append(InlineKeyboardButton(t("mode.br_btn", lang), callback_data="ua_browse_mode_br"))
    if 'mp' in enabled_modes:
        mode_buttons.append(InlineKeyboardButton(t("mode.mp_btn", lang), callback_data="ua_browse_mode_mp"))
    
    if not mode_buttons:
        await query.edit_message_text(
            t('ua.error.no_active_modes', lang),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_menu")]
            ])
        )
        return
    
    # اگر یکی باشه، تک تک
    for btn in mode_buttons:
        keyboard.append([btn])
    
    keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_menu")])
    
    await query.edit_message_text(
        f"{t('ua.browse', lang)}\n\n" + t('mode.choose', lang),
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def browse_mode_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب مود برای Browse"""
    query = update.callback_query
    await query.answer()
    
    mode = query.data.split('_')[-1]  # br یا mp
    context.user_data['browse_mode'] = mode
    
    lang = get_user_lang(update, context, db) or 'fa'
    mode_name = t(f"mode.{mode}_btn", lang)
    
    # منوی فیلتر: همه یا انتخاب دسته
    keyboard = [
        [InlineKeyboardButton(t("list.show", lang), callback_data=f"ua_browse_all_{mode}")],
        [InlineKeyboardButton(t("category.choose", lang), callback_data=f"ua_browse_select_cat_{mode}")],
        [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_browse")]
    ]
    
    await query.edit_message_text(
        f"{t('mode.label', lang)}: {mode_name}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def browse_show_category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی انتخاب دسته‌بندی"""
    query = update.callback_query
    await query.answer()
    
    mode = query.data.split('_')[-1]  # br یا mp
    context.user_data['browse_mode'] = mode
    
    lang = get_user_lang(update, context, db) or 'fa'
    mode_name = t(f"mode.{mode}_btn", lang)
    
    # فیلتر کردن دسته‌های فعال برای mode انتخاب شده
    from config.config import is_category_enabled
    active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() if is_category_enabled(k, mode)}
    
    if not active_categories:
        await query.edit_message_text(
            f"{t('mode.label', lang)}: {mode_name}\n\n" + t('category.none', lang),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_browse")]
            ])
        )
        return
    
    # نمایش دسته‌بندی‌ها
    keyboard = build_category_keyboard(
        active_categories,
        callback_prefix="ua_browse_cat_",
        show_count=False,
        db=None,
        lang=lang
    )
    keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"ua_browse_mode_{mode}")])
    
    await query.edit_message_text(
        f"{t('mode.label', lang)}: {mode_name}\n" + t('category.choose', lang),
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def browse_show_all_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش همه اتچمنت‌ها (تمام دسته‌ها)"""
    query = update.callback_query
    await query.answer()
    
    mode = query.data.split('_')[-1]  # br یا mp
    context.user_data['browse_mode'] = mode
    context.user_data['browse_category'] = 'all'  # علامت همه دسته‌ها
    
    # فیلتر کردن دسته‌های فعال برای mode انتخاب شده
    from config.config import is_category_enabled
    enabled_categories = [k for k in WEAPON_CATEGORIES.keys() if is_category_enabled(k, mode)]
    
    # دریافت همه اتچمنت‌های approved این مود
    try:
        # ساخت WHERE clause براساس دسته‌های فعال
        if enabled_categories:
            # Build a proper placeholders list for psycopg
            placeholders = ','.join(['%s'] * len(enabled_categories))
            query_sql = f"""
                SELECT ua.*, u.username, u.first_name
                FROM user_attachments ua
                LEFT JOIN users u ON ua.user_id = u.user_id
                WHERE ua.mode = %s AND ua.status = 'approved' AND ua.category IN ({placeholders})
                ORDER BY ua.like_count DESC, ua.approved_at DESC
            """
            params = (mode,) + tuple(enabled_categories)
        else:
            # اگر لیست خالی بود، همه رو نشون بده
            query_sql = """
                SELECT ua.*, u.username, u.first_name
                FROM user_attachments ua
                LEFT JOIN users u ON ua.user_id = u.user_id
                WHERE ua.mode = %s AND ua.status = 'approved'
                ORDER BY ua.like_count DESC, ua.approved_at DESC
            """
            params = (mode,)
        
        # Use proper connection context manager and cursor (DatabaseAdapter pooled)
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query_sql, params)
            rows = cursor.fetchall()
            cursor.close()
        attachments = [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching all user attachments: {e}")
        attachments = []
    
    if not attachments:
        lang = get_user_lang(update, context, db) or 'fa'
        mode_name = t(f"mode.{mode}_btn", lang)
        await query.edit_message_text(
            f"{t('mode.label', lang)}: {mode_name}\n\n" + t('attachment.none', lang),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t("ua.submit", lang), callback_data="ua_submit"),
                InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"ua_browse_mode_{mode}")
            ]])
        )
        return
    
    # ذخیره برای pagination
    context.user_data['browse_attachments'] = attachments
    context.user_data['browse_page'] = 0
    
    # نمایش صفحه اول
    await show_attachments_page(update, context)


async def browse_category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب دسته - نمایش مستقیم اتچمنت‌ها"""
    query = update.callback_query
    await query.answer()
    
    category = query.data.replace('ua_browse_cat_', '')
    context.user_data['browse_category'] = category
    
    mode = context.user_data['browse_mode']
    
    # دریافت اتچمنت‌های approved این دسته
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
            SELECT ua.*, u.username, u.first_name
            FROM user_attachments ua
            LEFT JOIN users u ON ua.user_id = u.user_id
            WHERE ua.category = %s AND ua.mode = %s AND ua.status = 'approved'
            ORDER BY ua.like_count DESC, ua.approved_at DESC
                """,
                (category, mode),
            )
            rows = cursor.fetchall()
            cursor.close()
        attachments = [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error fetching user attachments: {e}")
        attachments = []
    
    if not attachments:
        lang = get_user_lang(update, context, db) or 'fa'
        category_name = t(f"category.{category}", lang)
        await query.edit_message_text(
            f"{t('category.label', lang)}: {category_name}\n\n" + t('attachment.none', lang),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t("ua.submit", lang), callback_data="ua_submit"),
                InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"ua_browse_mode_{mode}")
            ]])
        )
        return
    
    # ذخیره برای pagination
    context.user_data['browse_attachments'] = attachments
    context.user_data['browse_page'] = 0
    
    # نمایش صفحه اول
    await show_attachments_page(update, context)


async def show_attachments_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش یک صفحه از اتچمنت‌ها"""
    query = update.callback_query
    if query:
        await query.answer()
    
    attachments = context.user_data.get('browse_attachments', [])
    page = context.user_data.get('browse_page', 0)
    lang = get_user_lang(update, context, db) or 'fa'
    mode_name = t(f"mode.{context.user_data['browse_mode']}_btn", lang)
    category = context.user_data.get('browse_category', '')
    cat_display = t('ua.all_categories', lang) if category == 'all' else WEAPON_CATEGORIES_SHORT.get(category, category)
    
    total_pages = (len(attachments) - 1) // ATTACHMENTS_PER_PAGE + 1
    start_idx = page * ATTACHMENTS_PER_PAGE
    end_idx = min(start_idx + ATTACHMENTS_PER_PAGE, len(attachments))
    
    page_attachments = attachments[start_idx:end_idx]
    
    # ساخت پیام
    message = (
        f"{t('mode.label', lang)}: {mode_name} › {cat_display}\n"
        f"{t('ua.browse', lang)}\n\n"
        f"{t('pagination.showing_range', lang, start=start_idx+1, end=end_idx, total=len(attachments))}\n"
        f"{t('pagination.page_of', lang, page=page+1, total=total_pages)}\n\n"
    )
    
    # ساخت کیبورد
    keyboard = []
    
    for att in page_attachments:
        weapon = att.get('custom_weapon_name') or t('common.unknown', lang)
        att_name = att.get('name') or att.get('attachment_name') or t('common.unknown', lang)
        likes = att.get('like_count', 0)
        username = (att.get('username') or att.get('first_name') or t('user.anonymous', lang))
        cat_key = att.get('category', '')
        
        # اگر همه دسته‌ها: نمایش مخفف دسته
        if category == 'all':
            cat_short = WEAPON_CATEGORIES_SHORT.get(cat_key, cat_key)
            button_text = f"{cat_short} [{weapon}] {att_name[:15]} - @{username}"
        else:
            # فرمت بدون دسته
            button_text = f"[{weapon}] {att_name[:20]} - @{username}"
        
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"ua_view_{att['id']}"
            )
        ])
    
    # دکمه‌های pagination
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(t('nav.prev', lang), callback_data="ua_browse_prev"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(t('nav.next', lang), callback_data="ua_browse_next"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"ua_browse_mode_{context.user_data['browse_mode']}")])
    
    if query:
        try:
            await query.edit_message_text(
                message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            # اگر پیام photo بود، نمیشه edit کرد
            # پس delete کن و پیام جدید بفرست
            try:
                await query.message.delete()
            except Exception as e:
                logger.warning(f"Failed to delete previous browse message: {e}")
            await update.effective_chat.send_message(
                message,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        await update.message.reply_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def browse_prev_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """صفحه قبل"""
    context.user_data['browse_page'] = max(0, context.user_data.get('browse_page', 0) - 1)
    await show_attachments_page(update, context)


async def browse_next_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """صفحه بعد"""
    attachments = context.user_data.get('browse_attachments', [])
    total_pages = (len(attachments) - 1) // ATTACHMENTS_PER_PAGE + 1
    current_page = context.user_data.get('browse_page', 0)
    
    context.user_data['browse_page'] = min(total_pages - 1, current_page + 1)
    await show_attachments_page(update, context)


async def view_attachment_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات یک اتچمنت"""
    query = update.callback_query
    await query.answer()
    
    attachment_id = int(query.data.replace('ua_view_', ''))
    
    # دریافت اتچمنت
    attachment = db.get_user_attachment(attachment_id)
    
    if not attachment:
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('attachment.not_found', lang), show_alert=True)
        return
    
    # افزایش view_count
    try:
        with db.transaction() as conn:
            conn.execute("""
                UPDATE user_attachments 
                SET view_count = view_count + 1 
                WHERE id = %s
            """, (attachment_id,))
    except Exception as e:
        logger.error(f"Error updating view count: {e}")
    
    # ساخت پیام
    from telegram.helpers import escape_markdown
    
    lang = get_user_lang(update, context, db) or 'fa'
    username = attachment.get('username') or attachment.get('first_name') or t('user.anonymous', lang)
    description = attachment.get('description') or t('common.no_description', lang)
    views = attachment.get('view_count', 0) + 1
    
    mode_name = t(f"mode.{attachment['mode']}_short", lang)
    
    # Escape for MarkdownV2
    att_name = escape_markdown(str(attachment['attachment_name']), version=2)
    mode_name_esc = escape_markdown(str(mode_name), version=2)
    weapon_name = escape_markdown(str(attachment.get('custom_weapon_name', attachment['weapon_name'])), version=2)
    
    # دریافت نام دسته با ترجمه
    category_key = attachment.get('category', attachment.get('category_name', ''))
    category_local = t(f"category.{category_key}", lang)
    category_name = escape_markdown(str(category_local), version=2)
    
    description_esc = escape_markdown(str(description), version=2)
    # Format submitted_at safely (datetime | date | str | None)
    sub_at = attachment.get('submitted_at')
    if isinstance(sub_at, datetime):
        sub_ts = sub_at.date().isoformat()
    elif isinstance(sub_at, date):
        sub_ts = sub_at.isoformat()
    elif isinstance(sub_at, str):
        sub_ts = sub_at[:10]
    else:
        sub_ts = t('common.unknown', lang)
    date_str = escape_markdown(sub_ts, version=2)
    
    caption = (
        f"📎 *{att_name}*\n\n"
        f"🎮 *{t('mode.label', lang)}:* {mode_name_esc}\n"
        f"🔫 *{t('weapon.label', lang)}:* {weapon_name}\n"
        f"📂 *{t('category.label', lang)}:* {category_name}\n\n"
        f"💬 *{escape_markdown(t('ua.view.description_label', lang), version=2)}:*\n{description_esc}\n\n"
        f"👤 *{escape_markdown(t('ua.view.sender_label', lang), version=2)}:* @{escape_markdown(str(username), version=2)}\n"
        f"👁 *{escape_markdown(t('ua.view.views_label', lang), version=2)}:* {views}\n"
        f"📅 *{escape_markdown(t('ua.view.date_label', lang), version=2)}:* {date_str}"
    )
    
    # بررسی اینکه کاربر قبلاً این پست را گزارش کرده یا نه، برای مخفی کردن دکمه گزارش
    already_reported = False
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    SELECT 1 FROM user_attachment_reports
                    WHERE attachment_id = %s AND reporter_id = %s
                    LIMIT 1
                    """,
                    (attachment_id, update.effective_user.id),
                )
            except Exception:
                cur.execute(
                    """
                    SELECT 1 FROM user_attachment_reports
                    WHERE attachment_id = %s AND user_id = %s
                    LIMIT 1
                    """,
                    (attachment_id, update.effective_user.id),
                )
            already_reported = cur.fetchone() is not None
    except Exception as _pre_err:
        logger.error(f"Error prechecking already_reported: {_pre_err}")

    row1 = [InlineKeyboardButton("👍", callback_data=f"ua_like_{attachment_id}")]
    if not already_reported:
        row1.append(InlineKeyboardButton("⚠️", callback_data=f"ua_report_{attachment_id}"))
    keyboard = [
        row1,
        [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ua_browse_back")]
    ]
    
    # ارسال تصویر
    await query.message.reply_photo(
        photo=attachment['image_file_id'],
        caption=caption,
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # حذف پیام قبلی
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete previous attachment detail message: {e}")


async def like_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لایک اتچمنت"""
    query = update.callback_query
    
    attachment_id = int(query.data.replace('ua_like_', ''))
    
    try:
        with db.transaction() as conn:
            conn.execute("""
                UPDATE user_attachments 
                SET like_count = like_count + 1 
                WHERE id = %s
            """, (attachment_id,))
        
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('success.generic', lang), show_alert=True)
    except Exception as e:
        logger.error(f"Error liking attachment: {e}")
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('error.generic', lang), show_alert=True)


async def report_attachment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """گزارش اتچمنت"""
    query = update.callback_query
    
    attachment_id = int(query.data.replace('ua_report_', ''))
    reporter_id = update.effective_user.id
    
    # محدودیت‌ها: هر کاربر فقط یکبار برای هر پست، و حداکثر 5 گزارش در روز
    today_count = 0
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            # بررسی گزارش تکراری برای همان پست
            try:
                cur.execute(
                    """
                    SELECT 1 
                    FROM user_attachment_reports 
                    WHERE attachment_id = %s AND reporter_id = %s 
                    LIMIT 1
                    """,
                    (attachment_id, reporter_id),
                )
            except Exception:
                # سازگاری با اسکیما قدیمی (user_id به جای reporter_id)
                cur.execute(
                    """
                    SELECT 1 
                    FROM user_attachment_reports 
                    WHERE attachment_id = %s AND user_id = %s 
                    LIMIT 1
                    """,
                    (attachment_id, reporter_id),
                )
            dup = cur.fetchone()
            if dup:
                lang = get_user_lang(update, context, db) or 'fa'
                await query.answer(t('ua.report.duplicate', lang), show_alert=True)
                return
            
            # محدودیت ۵ گزارش در روز
            today_count = 0
            try:
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM user_attachment_reports 
                    WHERE reporter_id = %s AND reported_at >= CURRENT_DATE
                    """,
                    (reporter_id,),
                )
            except Exception:
                # سازگاری با ستون created_at
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM user_attachment_reports 
                    WHERE user_id = %s AND created_at >= CURRENT_DATE
                    """,
                    (reporter_id,),
                )
            row = cur.fetchone()
            today_count = int((row or {}).get('cnt') or 0)
            if today_count >= 5:
                lang = get_user_lang(update, context, db) or 'fa'
                await query.answer(t('ua.report.limit_reached', lang), show_alert=True)
                return
    except Exception as pre_err:
        logger.error(f"Precheck error on reporting attachment: {pre_err}")

    # ذخیره report (ساده)
    try:
        with db.transaction() as conn:
            # افزایش report_count
            conn.execute("""
                UPDATE user_attachments 
                SET report_count = report_count + 1 
                WHERE id = %s
            """, (attachment_id,))
            
            # ثبت در جدول reports (با fallback برای اسکیما قدیمی)
            try:
                conn.execute("""
                    INSERT INTO user_attachment_reports (attachment_id, reporter_id, reason, reported_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """, (attachment_id, reporter_id, 'محتوای نامناسب'))
            except Exception:
                conn.execute("""
                    INSERT INTO user_attachment_reports (attachment_id, user_id, reason, created_at)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                """, (attachment_id, reporter_id, 'محتوای نامناسب'))
        # بعد از ثبت گزارش، کش آمار را پاک می‌کنیم تا شمارنده‌ها به‌روز شوند
        try:
            cache.invalidate('stats')
        except Exception:
            pass
        used_now = (today_count or 0) + 1
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('ua.report.saved_today', lang, used=used_now), show_alert=True)
    except Exception as e:
        logger.error(f"Error reporting attachment: {e}")
        lang = get_user_lang(update, context, db) or 'fa'
        await query.answer(t('ua.report.duplicate', lang), show_alert=True)


async def browse_back_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به لیست"""
    query = update.callback_query
    await query.answer()
    
    # حذف پیام تصویر
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete browse image message: {e}")
    
    # نمایش مجدد لیست
    await show_attachments_page(update, context)


# Export handlers
browse_handlers = [
    CallbackQueryHandler(browse_attachments_menu, pattern="^ua_browse$"),
    CallbackQueryHandler(browse_mode_selected, pattern="^ua_browse_mode_(br|mp)$"),
    CallbackQueryHandler(browse_show_all_attachments, pattern="^ua_browse_all_(br|mp)$"),
    CallbackQueryHandler(browse_show_category_menu, pattern="^ua_browse_select_cat_(br|mp)$"),
    CallbackQueryHandler(browse_category_selected, pattern="^ua_browse_cat_(?!.*select)"),
    CallbackQueryHandler(browse_prev_page, pattern="^ua_browse_prev$"),
    CallbackQueryHandler(browse_next_page, pattern="^ua_browse_next$"),
    CallbackQueryHandler(view_attachment_detail, pattern="^ua_view_\\d+$"),
    CallbackQueryHandler(like_attachment, pattern="^ua_like_\\d+$"),
    CallbackQueryHandler(report_attachment, pattern="^ua_report_\\d+$"),
    CallbackQueryHandler(browse_back_to_list, pattern="^ua_browse_back$"),
]
