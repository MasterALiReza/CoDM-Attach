"""
هندلرهای مدیریت کانال‌های اجباری برای ادمین‌ها
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import logging
import os
from utils.analytics_pg import AnalyticsPostgres as Analytics
from utils.logger import log_exception
from handlers.admin.admin_handlers_modular import AdminHandlers
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text

logger = logging.getLogger(__name__)

# حالت‌های مدیریت کانال
CHANNEL_MENU = "CHANNEL_MENU"
ADD_CHANNEL_ID = "ADD_CHANNEL_ID"
ADD_CHANNEL_TITLE = "ADD_CHANNEL_TITLE"
ADD_CHANNEL_URL = "ADD_CHANNEL_URL"
ADD_CHANNEL_CONFIRM = "ADD_CHANNEL_CONFIRM"
EDIT_CHANNEL_SELECT = "EDIT_CHANNEL_SELECT"
EDIT_CHANNEL_FIELD = "EDIT_CHANNEL_FIELD"
EDIT_CHANNEL_VALUE = "EDIT_CHANNEL_VALUE"
DELETE_CHANNEL_CONFIRM = "DELETE_CHANNEL_CONFIRM"
REORDER_CHANNELS = "REORDER_CHANNELS"


def check_channel_management_permission(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """بررسی دسترسی مدیریت کانال‌ها با استفاده از RBAC"""
    from core.security.role_manager import Permission
    
    # دریافت role_manager از context
    role_manager = context.bot_data.get('role_manager')
    if not role_manager:
        # fallback: بررسی ادمین بودن از database
        db = context.bot_data.get('database')
        if db:
            return db.is_admin(user_id)
        
        # fallback نهایی به سیستم قدیمی
        from config import ADMIN_IDS
        admins = context.bot_data.get('admins', ADMIN_IDS)
        return user_id in admins
    
    # بررسی دسترسی MANAGE_CHANNELS یا super_admin
    if role_manager.is_super_admin(user_id):
        return True
    
    return role_manager.has_permission(user_id, Permission.MANAGE_CHANNELS)


# تنظیمات Pagination
CHANNELS_PER_PAGE = 8  # تعداد کانال در هر صفحه


def paginate_list(items: list, page: int, per_page: int) -> tuple:
    """
    صفحه‌بندی لیست
    
    Returns:
        tuple: (items_in_page, total_pages, has_prev, has_next)
    """
    total_items = len(items)
    total_pages = (total_items + per_page - 1) // per_page  # Round up
    
    # اعتبارسنجی page
    page = max(1, min(page, total_pages if total_pages > 0 else 1))
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    
    items_in_page = items[start_idx:end_idx]
    has_prev = page > 1
    has_next = page < total_pages
    
    return items_in_page, total_pages, has_prev, has_next


async def noop_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پاسخ به دکمه‌های بدون عملیات برای جلوگیری از خطا."""
    try:
        await update.callback_query.answer()
    except Exception:
        pass


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منوی مدیریت کانال‌ها از هر وضعیت."""
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    # اگر از طریق Callback آمده
    query = getattr(update, 'callback_query', None)
    if query:
        try:
            await query.answer()
        except Exception:
            pass
        # نمایش منوی اصلی مدیریت کانال‌ها
        return await channel_management_menu(update, context)
    # اگر از طریق /cancel آمده
    msg = getattr(update, 'message', None)
    if msg:
        try:
            await msg.reply_text(t('menu.buttons.back', lang))
        except Exception:
            pass
        return await channel_management_menu(update, context)
    # پیشفرض: پایان
    return ConversationHandler.END

async def channel_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1):
    """منوی اصلی مدیریت کانال‌ها (با Pagination)"""
    # تعیین زبان برای پیام‌های خطا/اعلان
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    if not check_channel_management_permission(update.effective_user.id, context):
        query = update.callback_query
        if query:
            await query.answer(t('admin.channels.permission_denied', lang), show_alert=True)
        else:
            try:
                await update.message.reply_text(t('admin.channels.permission_denied', lang))
            except Exception:
                pass
        return ConversationHandler.END
    
    logger.info("[channel] Open menu by user=%s, page=%d", update.effective_user.id, page)
    query = update.callback_query
    if query:
        await query.answer()
    
    db = context.bot_data['database']
    # تعیین زبان (بازنویسی با دیتابیس قطعی در صورت نیاز)
    try:
        lang = get_user_lang(update, context, db) or lang
    except Exception:
        pass
    all_channels = db.get_required_channels()
    
    keyboard = []
    
    # Pagination کانال‌ها
    channels = []
    total_pages = 0
    if all_channels:
        channels, total_pages, has_prev, has_next = paginate_list(
            all_channels, page, CHANNELS_PER_PAGE
        )
        
        keyboard.append([InlineKeyboardButton(
            t('admin.channels.pagination.header', lang, page=page, total=total_pages),
            callback_data="noop"
        )])
        
        # نمایش کانال‌های صفحه فعلی
        for channel in channels:
            keyboard.append([
                InlineKeyboardButton(
                    f"📢 {channel['title']}",
                    callback_data=f"view_channel_{channel['channel_id']}"
                )
            ])
        
        # دکمه‌های Navigation (اگر بیش از یک صفحه باشه)
        if total_pages > 1:
            nav_buttons = []
            if has_prev:
                nav_buttons.append(InlineKeyboardButton(
                    t('nav.prev', lang),
                    callback_data=f"ch_page_{page-1}"
                ))
            
            nav_buttons.append(InlineKeyboardButton(
                f"{page}/{total_pages}",
                callback_data="noop"
            ))
            
            if has_next:
                nav_buttons.append(InlineKeyboardButton(
                    t('nav.next', lang),
                    callback_data=f"ch_page_{page+1}"
                ))
            
            keyboard.append(nav_buttons)
    
    # دکمه‌های عملیات
    keyboard.append([
        InlineKeyboardButton(t('admin.channels.buttons.add', lang), callback_data="add_channel")
    ])
    
    if channels:
        keyboard.append([
            InlineKeyboardButton(t('admin.channels.buttons.edit', lang), callback_data="edit_channel"),
            InlineKeyboardButton(t('admin.channels.buttons.delete', lang), callback_data="delete_channel")
        ])
        keyboard.append([
            InlineKeyboardButton(t('admin.channels.buttons.reorder', lang), callback_data="reorder_channels"),
            InlineKeyboardButton(t('admin.channels.buttons.clear_all', lang), callback_data="clear_channels")
        ])
    
    keyboard.append([
        InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="ch_admin_return")
    ])
    
    message = t('admin.channels.menu.title', lang) + "\n\n"
    if all_channels:
        message += t('admin.channels.menu.total', lang, n=len(all_channels)) + "\n"
        
        if total_pages > 1:
            start_num = (page - 1) * CHANNELS_PER_PAGE + 1
            end_num = min(page * CHANNELS_PER_PAGE, len(all_channels))
            message += t('pagination.showing_range', lang, start=start_num, end=end_num, total=len(all_channels)) + "\n"
        
        message += "\n" + t('admin.channels.menu.hint_click', lang) + "\n"
        message += t('admin.channels.menu.hint_membership', lang)
    else:
        message += t('admin.channels.menu.empty', lang) + "\n\n"
        message += t('admin.channels.menu.empty_hint', lang)
    
    if query:
        await safe_edit_message_text(
            query,
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    
    return CHANNEL_MENU


async def clear_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پاک‌کردن همه کانال‌های اجباری با تایید"""
    query = update.callback_query
    await query.answer()
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    
    db = context.bot_data['database']
    if query.data == "clear_channels":
        keyboard = [[
            InlineKeyboardButton(t('admin.channels.delete.confirm_yes', lang), callback_data="clear_yes"),
            InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")
        ]]
        await safe_edit_message_text(
            query,
            t('admin.channels.clear.confirm', lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return CHANNEL_MENU
    
    # تایید حذف همه
    channels = db.get_required_channels()
    success_all = True
    for ch in channels:
        try:
            ok = db.remove_required_channel(ch['channel_id'])
            success_all = success_all and ok
        except Exception:
            success_all = False
    
    if success_all:
        try:
            from managers.channel_manager import invalidate_all_cache
            cleared_count = invalidate_all_cache()
            logger.info(f"[channel] Cleared all channels; invalidated cache for {cleared_count} users")
        except Exception as e:
            logger.error(f"[channel] Error invalidating cache after clear: {e}")
    
    msg = t('admin.channels.clear.success', lang) if success_all else t('admin.channels.clear.error', lang)
    keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]]
    await safe_edit_message_text(
        query,
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHANNEL_MENU


async def handle_page_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """هندلر برای navigation بین صفحات کانال‌ها"""
    query = update.callback_query
    
    # استخراج شماره صفحه از callback_data
    page = int(query.data.split("_")[2])
    
    # نمایش صفحه جدید
    return await channel_management_menu(update, context, page=page)


async def view_channel_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش جزئیات یک کانال"""
    query = update.callback_query
    await query.answer()
    # زبان برای پیام‌ها
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    
    channel_id = query.data.split("_")[2]
    db = context.bot_data['database']
    
    channel = db.get_channel_by_id(channel_id)
    
    if not channel:
        await query.answer(t('admin.channels.not_found', lang), show_alert=True)
        return await channel_management_menu(update, context)
    
    is_active = channel.get('is_active', True)
    status_emoji = "✅" if is_active else "❌"
    status_text_i18n = t('admin.channels.status.active', lang) if is_active else t('admin.channels.status.inactive', lang)
    
    message = (
        t('admin.channels.details.title', lang) + "\n\n" +
        t('admin.channels.details.name', lang, title=channel['title']) + "\n" +
        t('admin.channels.details.id', lang, id=channel['channel_id']) + "\n" +
        t('admin.channels.details.url', lang, url=channel['url']) + "\n" +
        t('admin.channels.details.status', lang, emoji=status_emoji, status=status_text_i18n) + "\n"
    )
    
    # دکمه toggle با emoji و متن مناسب
    toggle_emoji = "🔴" if is_active else "🟢"
    toggle_text = t('admin.channels.buttons.toggle_deactivate', lang) if is_active else t('admin.channels.buttons.toggle_activate', lang)
    keyboard = [
        [InlineKeyboardButton(f"{toggle_emoji} {toggle_text}", callback_data=f"toggle_channel_{channel_id}")],
        [
            InlineKeyboardButton(t('admin.channels.buttons.stats', lang), callback_data=f"channel_stat_{channel_id}"),
            InlineKeyboardButton(t('admin.channels.buttons.test', lang), callback_data=f"test_channel_{channel_id}")
        ],
        [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]
    ]
    
    await safe_edit_message_text(
        query,
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return CHANNEL_MENU


async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع فرآیند افزودن کانال جدید"""
    query = update.callback_query
    await query.answer()
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    message = (
        t('admin.channels.add.title', lang) + "\n\n" +
        t('admin.channels.add.prompt_id', lang) + "\n" +
        t('admin.channels.add.example_id', lang) + "\n\n" +
        t('admin.channels.add.note_bot_admin', lang)
    )
    keyboard = [[InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return ADD_CHANNEL_ID


async def add_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت آیدی کانال"""
    if not update.message or not update.message.text:
        return ADD_CHANNEL_ID
    
    channel_id = update.message.text.strip()
    logger.info(f"[channel] Received channel ID: {channel_id} from user={update.effective_user.id}")
    
    # اعتبارسنجی دقیق آیدی کانال
    from utils.validators import validate_channel_id
    is_valid, error_or_value = validate_channel_id(channel_id)
    
    if not is_valid:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        keyboard = [[InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")]]
        await update.message.reply_text(
            f"❌ {error_or_value}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADD_CHANNEL_ID
    
    # استفاده از مقدار validated
    channel_id = error_or_value
    
    # بررسی عضویت ربات در کانال
    try:
        chat = await context.bot.get_chat(channel_id)
        channel_title = chat.title
        
        # ذخیره اطلاعات موقت
        context.user_data['temp_channel'] = {
            'channel_id': str(chat.id),
            'title': channel_title
        }
        
        logger.info(f"[channel] Successfully verified channel {channel_title} ({chat.id})")
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        message = (
            t('admin.channels.add.found', lang, title=channel_title) + "\n\n" +
            t('admin.channels.add.prompt_title', lang) + "\n" +
            t('admin.channels.add.default_title_label', lang, title=channel_title)
        )
        keyboard = [
            [InlineKeyboardButton(t('admin.channels.use_default_title', lang), callback_data="use_default_title")],
            [InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")]
        ]
        
        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        
        return ADD_CHANNEL_TITLE
        
    except Exception as e:
        logger.error(f"[channel] Error accessing channel {channel_id}: {e}")
        log_exception(logger, e, {"channel_id": channel_id, "user_id": update.effective_user.id})
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]]
        await update.message.reply_text(
            t('admin.channels.errors.access_channel', lang, err=str(e)),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
        return ADD_CHANNEL_ID


async def use_default_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استفاده از نام پیش‌فرض کانال"""
    query = update.callback_query
    await query.answer()
    
    temp_channel = context.user_data.get('temp_channel')
    if not temp_channel:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await safe_edit_message_text(query, t('admin.channels.errors.missing_temp', lang))
        return ConversationHandler.END
    
    # استفاده از نام پیش‌فرض
    context.user_data['temp_channel']['display_title'] = temp_channel['title']
    
    # ادامه به مرحله URL
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    message = (
        t('admin.channels.add.url.title', lang) + "\n\n" +
        t('admin.channels.add.url.prompt', lang) + "\n" +
        t('admin.channels.add.url.example', lang)
    )
    keyboard = [[InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return ADD_CHANNEL_URL


async def add_channel_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت عنوان نمایشی کانال"""
    if not update.message or not update.message.text:
        return ADD_CHANNEL_TITLE
    
    title = update.message.text.strip()
    logger.info(f"[channel] Received channel title: {title} from user={update.effective_user.id}")
    
    if not title:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        keyboard = [[InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")]]
        await update.message.reply_text(
            t('admin.channels.errors.empty_title', lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADD_CHANNEL_TITLE
    
    context.user_data['temp_channel']['display_title'] = title
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    message = (
        t('admin.channels.add.url.title', lang) + "\n\n" +
        t('admin.channels.add.url.prompt', lang) + "\n" +
        t('admin.channels.add.url.example', lang)
    )
    keyboard = [[InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")]]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return ADD_CHANNEL_URL


async def add_channel_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت لینک کانال و ذخیره"""
    if not update.message or not update.message.text:
        return ADD_CHANNEL_URL
    
    url = update.message.text.strip()
    logger.info(f"[channel] Received channel URL: {url} from user={update.effective_user.id}")
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    if not url.startswith('https://t.me/'):
        keyboard = [[InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")]]
        await update.message.reply_text(
            t('admin.channels.errors.invalid_link', lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADD_CHANNEL_URL
    
    temp_channel = context.user_data.get('temp_channel')
    if not temp_channel:
        await update.message.reply_text(t('admin.channels.errors.missing_temp', lang))
        return ConversationHandler.END
    
    # ذخیره URL در داده موقت
    context.user_data['temp_channel']['url'] = url
    
    # نمایش تاییدیه
    message = (
        t('admin.channels.add.confirm.title', lang) + "\n\n" +
        t('admin.channels.add.confirm.body', lang, 
          title=temp_channel['display_title'],
          url=url,
          id=temp_channel['channel_id'])
    )
    
    keyboard = [
        [InlineKeyboardButton(t('admin.channels.add.confirm.save', lang), callback_data="save_channel")],
        [InlineKeyboardButton(t('admin.channels.add.confirm.edit', lang), callback_data="add_channel")], # Restart flow
        [InlineKeyboardButton(t('admin.channels.add.confirm.cancel', lang), callback_data="channel_menu")]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return ADD_CHANNEL_CONFIRM


async def save_channel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ذخیره نهایی کانال پس از تایید"""
    query = update.callback_query
    await query.answer()
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
        
    temp_channel = context.user_data.get('temp_channel')
    if not temp_channel or 'url' not in temp_channel:
        await safe_edit_message_text(query, t('admin.channels.errors.missing_temp', lang))
        return ConversationHandler.END
        
    # ذخیره در دیتابیس
    db = context.bot_data['database']
    success = db.add_required_channel(
        channel_id=temp_channel['channel_id'],
        title=temp_channel['display_title'],
        url=temp_channel['url']
    )
    
    if success:
        logger.info(f"[channel] Successfully added channel {temp_channel['channel_id']} by user={update.effective_user.id}")
        
        # پاک کردن cache تمام کاربران (کانال جدید اضافه شده)
        from managers.channel_manager import invalidate_all_cache
        cleared_count = invalidate_all_cache()
        logger.info(f"[channel] Cleared membership cache for {cleared_count} users after adding channel")
        
        # Analytics: ثبت افزودن کانال
        try:
            analytics = Analytics()
            analytics.track_channel_added(
                channel_id=temp_channel['channel_id'],
                title=temp_channel['display_title'],
                url=temp_channel['url'],
                admin_id=update.effective_user.id
            )
        except Exception as e:
            logger.error(f"[Analytics] Error tracking channel added: {e}")
            log_exception(logger, e, {"channel_id": temp_channel['channel_id'], "admin_id": update.effective_user.id})
        
        message = t('admin.channels.add.success', lang)
    else:
        logger.error(f"[channel] Failed to add channel {temp_channel['channel_id']} - possibly duplicate")
        message = t('admin.channels.add.save_error', lang)
    
    keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]]
    
    await safe_edit_message_text(
        query,
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    # پاک کردن داده موقت
    context.user_data.pop('temp_channel', None)
    
    return CHANNEL_MENU


async def edit_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع ویرایش کانال"""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data['database']
    channels = db.get_required_channels()
    
    if not channels:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.answer(t('admin.channels.edit.none', lang), show_alert=True)
        return await channel_management_menu(update, context)
    
    keyboard = []
    for channel in channels:
        keyboard.append([
            InlineKeyboardButton(
                f"📢 {channel['title']}",
                callback_data=f"edit_select_{channel['channel_id']}"
            )
        ])
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")])
    
    await safe_edit_message_text(
        query,
        t('admin.channels.edit.title', lang) + "\n\n" + t('admin.channels.edit.prompt', lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return EDIT_CHANNEL_SELECT


async def edit_channel_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب فیلد برای ویرایش"""
    query = update.callback_query
    await query.answer()
    
    channel_id = query.data.split("_")[2]
    context.user_data['editing_channel_id'] = channel_id
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    keyboard = [
        [InlineKeyboardButton(t('admin.channels.buttons.edit_title', lang), callback_data="edit_field_title")],
        [InlineKeyboardButton(t('admin.channels.buttons.edit_url', lang), callback_data="edit_field_url")],
        [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="edit_channel")]
    ]
    
    await safe_edit_message_text(
        query,
        t('admin.channels.edit.choose_field', lang),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return EDIT_CHANNEL_FIELD


async def edit_channel_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت فیلد برای ویرایش"""
    query = update.callback_query
    await query.answer()
    
    field = query.data.split("_")[2]
    context.user_data['editing_field'] = field
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    if field == "title":
        message = t('admin.channels.edit.prompt_title', lang)
    else:
        message = t('admin.channels.edit.prompt_url', lang)
    keyboard = [[InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")]]
    
    await safe_edit_message_text(
        query,
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return EDIT_CHANNEL_VALUE


async def edit_channel_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ذخیره مقدار جدید"""
    if not update.message or not update.message.text:
        return EDIT_CHANNEL_VALUE
    
    value = update.message.text.strip()
    
    channel_id = context.user_data.get('editing_channel_id')
    field = context.user_data.get('editing_field')
    
    if not channel_id or not field:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await update.message.reply_text(t('admin.channels.errors.missing_edit', lang))
        return ConversationHandler.END
    
    db = context.bot_data['database']
    
    if field == "title":
        success = db.update_required_channel(channel_id, title=value)
        # Analytics: ثبت ویرایش
        if success:
            try:
                analytics = Analytics()
                analytics.track_channel_updated(
                    channel_id=channel_id,
                    admin_id=update.effective_user.id,
                    title=value
                )
            except Exception as e:
                logger.error(f"[Analytics] Error tracking channel update: {e}")
                log_exception(logger, e, {"channel_id": channel_id, "admin_id": update.effective_user.id})
    else:
        if not value.startswith('https://t.me/'):
            try:
                lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
            except Exception:
                lang = 'fa'
            await update.message.reply_text(
                t('admin.channels.errors.invalid_link', lang)
            )
            return EDIT_CHANNEL_VALUE
        success = db.update_required_channel(channel_id, url=value)
        # Analytics: ثبت ویرایش
        if success:
            try:
                analytics = Analytics()
                analytics.track_channel_updated(
                    channel_id=channel_id,
                    admin_id=update.effective_user.id,
                    url=value
                )
            except Exception as e:
                logger.error(f"[Analytics] Error tracking channel update: {e}")
                log_exception(logger, e, {"channel_id": channel_id, "admin_id": update.effective_user.id})
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    message = t('admin.channels.edit.success', lang) if success else t('admin.channels.edit.error', lang)
    keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # پاک کردن داده‌های موقت
    context.user_data.pop('editing_channel_id', None)
    context.user_data.pop('editing_field', None)
    
    return CHANNEL_MENU


async def delete_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع حذف کانال"""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data['database']
    channels = db.get_required_channels()
    
    if not channels:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.answer(t('admin.channels.delete.none', lang), show_alert=True)
        return await channel_management_menu(update, context)
    
    keyboard = []
    for channel in channels:
        keyboard.append([
            InlineKeyboardButton(
                f"🗑 {channel['title']}",
                callback_data=f"del_confirm_{channel['channel_id']}"
            )
        ])
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")])
    
    await safe_edit_message_text(
        query,
        t('admin.channels.delete.title', lang) + "\n\n" + t('admin.channels.delete.prompt', lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return DELETE_CHANNEL_CONFIRM

async def delete_channel_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید حذف کانال"""
    query = update.callback_query
    await query.answer()
    
    channel_id = query.data.split("_")[2]
    context.user_data['deleting_channel_id'] = channel_id
    
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    keyboard = [
        [
            InlineKeyboardButton(t('admin.channels.delete.confirm_yes', lang), callback_data="del_yes"),
            InlineKeyboardButton(t('menu.buttons.cancel', lang), callback_data="channel_menu")
        ]
    ]
    
    await safe_edit_message_text(
        query,
        t('admin.channels.delete.confirm', lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return DELETE_CHANNEL_CONFIRM


async def delete_channel_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرای حذف کانال"""
    query = update.callback_query
    await query.answer()
    
    channel_id = context.user_data.get('deleting_channel_id')
    if not channel_id:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.answer(t('admin.channels.errors.missing_temp', lang), show_alert=True)
        return ConversationHandler.END
    
    db = context.bot_data['database']
    success = db.remove_required_channel(channel_id)
    
    if success:
        # پاک کردن cache تمام کاربران (کانال حذف شده)
        from managers.channel_manager import invalidate_all_cache
        cleared_count = invalidate_all_cache()
        logger.info(f"[channel] Cleared membership cache for {cleared_count} users after removing channel")
        
        # Analytics: ثبت حذف کانال
        try:
            analytics = Analytics()
            analytics.track_channel_removed(
                channel_id=channel_id,
                admin_id=update.effective_user.id
            )
        except Exception as e:
            logger.error(f"[Analytics] Error tracking channel removed: {e}")
            log_exception(logger, e, {"channel_id": channel_id, "admin_id": update.effective_user.id})
        
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        message = t('admin.channels.delete.success', lang)
    else:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        message = t('admin.channels.delete.error', lang)
    
    keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]]
    
    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    context.user_data.pop('deleting_channel_id', None)
    
    return CHANNEL_MENU


async def toggle_channel_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تغییر وضعیت فعال/غیرفعال کانال"""
    query = update.callback_query
    await query.answer()
    
    channel_id = "_".join(query.data.split("_")[2:])  # toggle_channel_-1001234567890
    db = context.bot_data['database']
    
    if db.toggle_channel_status(channel_id):
        # پاک کردن cache تمام کاربران (وضعیت کانال تغییر کرده)
        from managers.channel_manager import invalidate_all_cache
        cleared_count = invalidate_all_cache()
        logger.info(f"[channel] Cleared membership cache for {cleared_count} users after toggling channel status")
        
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.answer(t('admin.channels.toggled', lang), show_alert=True)
        # نمایش مجدد جزئیات با وضعیت جدید
        # تغییر callback_data برای view
        update.callback_query.data = f"view_channel_{channel_id}"
        return await view_channel_details(update, context)
    else:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.answer(t('admin.channels.toggle_error', lang), show_alert=True)
        return CHANNEL_MENU


async def show_single_channel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش آمار یک کانال خاص"""
    query = update.callback_query
    await query.answer()
    
    # استخراج channel_id از callback_data
    channel_id = "_".join(query.data.split("_")[2:])  # channel_stat_-1001234567890
    
    try:
        analytics = Analytics()
        db = context.bot_data['database']
        
        # دریافت اطلاعات کانال از دیتابیس (حتی اگر غیرفعال باشد)
        channel = db.get_channel_by_id(channel_id)
        
        if not channel:
            try:
                lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
            except Exception:
                lang = 'fa'
            await query.answer(t('admin.channels.not_found', lang), show_alert=True)
            return await channel_management_menu(update, context)
        
        # دریافت آمار کانال
        stats = analytics.get_channel_stats(channel_id)
        
        if not stats:
            try:
                lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
            except Exception:
                lang = 'fa'
            message = t('admin.channels.stats.single.title', lang, title=channel['title']) + "\n\n"
            message += t('admin.channels.stats.single.no_data', lang)
        else:
            try:
                lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
            except Exception:
                lang = 'fa'
            message = t('admin.channels.stats.single.title', lang, title=channel['title']) + "\n\n"
            message += t('admin.channels.stats.single.joins', lang, n=stats.get('total_joins', 0)) + "\n"
            message += t('admin.channels.stats.single.attempts', lang, n=stats.get('total_join_attempts', 0)) + "\n"
            message += t('admin.channels.stats.single.conversion', lang, rate=stats.get('conversion_rate', 0)) + "\n\n"
            
            # تاریخ افزودن
            added_at = stats.get('added_at')
            if added_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(added_at)
                    date_text = dt.strftime('%Y/%m/%d - %H:%M')
                except Exception:
                    date_text = added_at[:10]
                message += t('admin.channels.stats.single.added_date', lang, date=date_text) + "\n"
            
            # وضعیت
            st = stats.get('status', 'active')
            status_text = t('admin.channels.status.active', lang) if st == 'active' else t('admin.channels.status.deleted', lang)
            status_emoji = '✅' if st == 'active' else '❌'
            message += t('admin.channels.details.status', lang, emoji=status_emoji, status=status_text) + "\n"
        
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        keyboard = [
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"view_channel_{channel_id}")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"[channel] Error showing single channel stats: {e}")
        log_exception(logger, e, {"channel_id": channel_id})
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await safe_edit_message_text(
            query,
            t('admin.channels.stats.error', lang, err=str(e)),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]])
        )
    
    return CHANNEL_MENU


async def show_channel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش آمار همه کانال‌های اجباری (dashboard کلی)"""
    query = update.callback_query
    await query.answer()
    
    try:
        analytics = Analytics()
        
        # دریافت dashboard
        dashboard_text = analytics.generate_admin_dashboard()
        
        # دکمه‌های navigation - Phase 2 features
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        keyboard = [
            [InlineKeyboardButton(t('admin.channels.stats.buttons.funnel', lang), callback_data="channel_funnel")],
            [InlineKeyboardButton(t('admin.channels.stats.buttons.period_report', lang), callback_data="channel_period_report")],
            [InlineKeyboardButton(t('admin.channels.stats.buttons.export_csv', lang), callback_data="channel_export_csv")],
            [InlineKeyboardButton(t('admin.channels.stats.buttons.history', lang), callback_data="channel_history")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]
        ]
        
        await safe_edit_message_text(
            query,
            dashboard_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"[channel] Error showing channel stats: {e}")
        log_exception(logger, e, {"action": "show_channel_stats"})
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.edit_message_text(
            t('admin.channels.stats.error', lang, err=str(e)),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="channel_menu")]])
        )
    
    return CHANNEL_MENU


async def show_funnel_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش تحلیل قیف تبدیل"""
    query = update.callback_query
    await query.answer()
    
    try:
        analytics = Analytics()
        funnel_text = analytics.generate_funnel_analysis()
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        keyboard = [[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]]
        await safe_edit_message_text(
            query,
            funnel_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"[channel] Error showing funnel: {e}")
        log_exception(logger, e, {"action": "show_funnel_analysis"})
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await safe_edit_message_text(
            query,
            t('admin.channels.funnel.error', lang),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]])
        )
    
    return CHANNEL_MENU


async def show_period_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش گزارش دوره‌ای (7 روز گذشته)"""
    query = update.callback_query
    await query.answer()
    
    try:
        analytics = Analytics()
        report_text = analytics.generate_period_report()
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        keyboard = [[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]]
        await safe_edit_message_text(
            query,
            report_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        logger.error(f"[channel] Error showing period report: {e}")
        log_exception(logger, e, {"action": "show_period_report"})
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await safe_edit_message_text(
            query,
            t('admin.channels.period.error', lang),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]])
        )
    
    return CHANNEL_MENU


async def export_analytics_csv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export آمار به CSV و ارسال فایل‌ها"""
    query = update.callback_query
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    await query.answer(t('admin.channels.export.creating', lang))
    
    try:
        analytics = Analytics()
        files = analytics.export_to_csv("all")
        
        if not files:
            await safe_edit_message_text(
                query,
                t('admin.channels.export.no_files', lang),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]])
            )
            return CHANNEL_MENU
        
        # ارسال فایل‌ها
        await safe_edit_message_text(
            query,
            t('admin.channels.export.sending', lang, count=len(files))
        )
        
        for file_path in files:
            with open(file_path, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=os.path.basename(file_path),
                    caption=f"📊 {os.path.basename(file_path)}"
                )
        
        keyboard = [[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]]
        await query.message.reply_text(
            t('admin.channels.export.success', lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"[channel] Error exporting CSV: {e}")
        log_exception(logger, e, {"action": "export_analytics_csv"})
        await safe_edit_message_text(
            query,
            t('admin.channels.export.error', lang),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]])
        )
    
    return CHANNEL_MENU


async def test_channel_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تست دسترسی ربات به کانال"""
    query = update.callback_query
    try:
        lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
    except Exception:
        lang = 'fa'
    await query.answer(t('admin.channels.test.running', lang))
    
    # استخراج channel_id
    channel_id = "_".join(query.data.split("_")[2:])
    
    db = context.bot_data['database']
    channels = db.get_required_channels()
    channel = next((ch for ch in channels if ch['channel_id'] == channel_id), None)
    
    if not channel:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.answer(t('admin.channels.not_found', lang), show_alert=True)
        return await channel_management_menu(update, context)
    
    # شروع تست
    test_results = []
    test_results.append(t('admin.channels.test.header', lang))
    test_results.append(t('admin.channels.test.channel_title', lang, title=channel['title']))
    
    # تست 1: بررسی وجود کانال
    try:
        chat = await context.bot.get_chat(channel_id)
        test_results.append(t('admin.channels.test.step1.channel_found', lang))
        test_results.append(t('admin.channels.test.step1.type', lang, type=chat.type))
        test_results.append(t('admin.channels.test.step1.name', lang, name=chat.title))
        
        # تست 2: بررسی admin بودن ربات
        try:
            bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
            
            if bot_member.status in ['administrator', 'creator']:
                test_results.append(t('admin.channels.test.step2.bot_is_admin', lang))
                test_results.append(t('admin.channels.test.step2.role', lang, role=bot_member.status))
                
                # بررسی دسترسی‌های ربات
                if hasattr(bot_member, 'can_post_messages'):
                    if bot_member.can_post_messages:
                        test_results.append(t('admin.channels.test.step2.can_post_true', lang))
                    else:
                        test_results.append(t('admin.channels.test.step2.can_post_false', lang))
                
                if hasattr(bot_member, 'can_invite_users'):
                    if bot_member.can_invite_users:
                        test_results.append(t('admin.channels.test.step2.can_invite_true', lang))
            else:
                test_results.append(t('admin.channels.test.step2.not_admin', lang, role=bot_member.status))
                test_results.append(t('admin.channels.test.step2.must_be_admin', lang))
        
        except Exception as e:
            test_results.append(t('admin.channels.test.step2.error_check', lang))
            test_results.append(t('admin.channels.test.error_detail', lang, err=str(e)))
        
        # تست 3: بررسی لینک دعوت
        test_results.append(t('admin.channels.test.step3.header', lang))
        if channel['url'].startswith('https://t.me/'):
            test_results.append(t('admin.channels.test.step3.link_ok', lang))
            
            # استخراج username از لینک
            username = channel['url'].replace('https://t.me/', '').split('?')[0]
            if username.startswith('+'):
                test_results.append(t('admin.channels.test.step3.link_private', lang))
            else:
                test_results.append(t('admin.channels.test.step3.link_public_user', lang, username=username))
        else:
            test_results.append(t('admin.channels.test.step3.link_invalid', lang))
        
        # تست 4: تعداد اعضا (اگر امکان‌پذیر باشد)
        try:
            member_count = await context.bot.get_chat_member_count(channel_id)
            test_results.append(t('admin.channels.test.step4.members_count', lang, n=f"{member_count:,}"))
        except Exception as e:
            logger.warning(f"[channel] Failed to get member count for {channel_id}: {e}")
        
        test_results.append(t('admin.channels.test.summary.success', lang))
        
    except Exception as e:
        error_type = type(e).__name__
        test_results.append(t('admin.channels.test.step1.error_access', lang))
        test_results.append(t('admin.channels.test.error_type', lang, type=error_type))
        test_results.append(t('admin.channels.test.error_message', lang, msg=str(e)))
        test_results.append(t('admin.channels.test.suggestions.header', lang))
        test_results.append(t('admin.channels.test.suggestions.check_id', lang))
        test_results.append(t('admin.channels.test.suggestions.bot_admin', lang))
        test_results.append(t('admin.channels.test.suggestions.channel_active', lang))
    
    keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"view_channel_{channel_id}")]]
    
    await query.edit_message_text(
        "\n".join(test_results),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return CHANNEL_MENU


async def reorder_channels_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی ترتیب دادن کانال‌ها"""
    query = update.callback_query
    await query.answer()
    
    db = context.bot_data['database']
    channels = db.get_required_channels()
    
    try:
        lang = get_user_lang(update, context, db) or 'fa'
    except Exception:
        lang = 'fa'
    if not channels:
        await query.answer(t('admin.channels.reorder.none', lang), show_alert=True)
        return await channel_management_menu(update, context)
    
    keyboard = []
    keyboard.append([InlineKeyboardButton(t('admin.channels.reorder.title', lang), callback_data="noop")])
    
    # نمایش کانال‌ها با دکمه‌های ↑↓
    for i, channel in enumerate(channels):
        # دکمه‌های move
        move_buttons = []
        
        # دکمه بالا (اگر اولین نباشد)
        if i > 0:
            move_buttons.append(InlineKeyboardButton("⬆️", callback_data=f"move_up_{channel['channel_id']}"))
        else:
            move_buttons.append(InlineKeyboardButton("  ", callback_data="noop"))
        
        # نام کانال
        move_buttons.append(InlineKeyboardButton(f"{i+1}. {channel['title']}", callback_data="noop"))
        
        # دکمه پایین (اگر آخرین نباشد)
        if i < len(channels) - 1:
            move_buttons.append(InlineKeyboardButton("⬇️", callback_data=f"move_down_{channel['channel_id']}"))
        else:
            move_buttons.append(InlineKeyboardButton("  ", callback_data="noop"))
        
        keyboard.append(move_buttons)
    
    keyboard.append([InlineKeyboardButton(t('admin.channels.reorder.confirm', lang), callback_data="channel_menu")])
    
    await query.edit_message_text(
        t('admin.channels.reorder.title', lang) + "\n\n" + t('admin.channels.reorder.instructions', lang),
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )
    
    return REORDER_CHANNELS


async def handle_move_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جابجایی کانال به بالا یا پایین"""
    query = update.callback_query
    
    # استخراج action و channel_id
    parts = query.data.split("_")
    if len(parts) < 3:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.answer(t('admin.channels.reorder.invalid_operation', lang), show_alert=True)
        return REORDER_CHANNELS
    
    action = "_".join(parts[:2])  # move_up یا move_down
    channel_id = "_".join(parts[2:])  # channel_id که ممکنه خودش underscore داشته باشه
    
    db = context.bot_data['database']
    
    if action == "move_up":
        success = db.move_channel_up(channel_id)
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        message = t('admin.channels.reorder.moved_up', lang) if success else t('admin.channels.reorder.move_up_failed', lang)
    elif action == "move_down":
        success = db.move_channel_down(channel_id)
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        message = t('admin.channels.reorder.moved_down', lang) if success else t('admin.channels.reorder.move_down_failed', lang)
    else:
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.answer(t('admin.channels.reorder.invalid_operation', lang), show_alert=True)
        return REORDER_CHANNELS
    
    await query.answer(message)
    
    if success:
        # پاک کردن cache تمام کاربران (ترتیب کانال‌ها تغییر کرده)
        from managers.channel_manager import invalidate_all_cache
        cleared_count = invalidate_all_cache()
        logger.info(f"[channel] Cleared membership cache for {cleared_count} users after reordering")
    
    # نمایش مجدد منوی reorder با ترتیب جدید
    return await reorder_channels_menu(update, context)


async def show_channel_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش تاریخچه کانال‌های حذف شده"""
    query = update.callback_query
    await query.answer()
    
    try:
        analytics = Analytics()
        
        # دریافت گزارش تاریخچه
        history_text = analytics.generate_channel_history_report()
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        keyboard = [[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]]
        
        await query.edit_message_text(
            history_text,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"[channel] Error showing channel history: {e}")
        log_exception(logger, e, {"action": "show_channel_history"})
        try:
            lang = get_user_lang(update, context, context.bot_data.get('database')) or 'fa'
        except Exception:
            lang = 'fa'
        await query.edit_message_text(
            t('admin.channels.history.error', lang),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t('admin.channels.history.back_to_stats', lang), callback_data="channel_stats")]])
        )
    
    return CHANNEL_MENU


async def return_to_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازگشت به منوی اصلی ادمین"""
    logger.info("[channel] Return to admin clicked by user=%s", update.effective_user.id)
    query = update.callback_query
    await query.answer()
    
    # پاک کردن داده‌های موقت
    context.user_data.pop('temp_channel', None)
    context.user_data.pop('editing_channel_id', None)
    context.user_data.pop('editing_field', None)
    context.user_data.pop('deleting_channel_id', None)
    context.user_data.pop('return_to_admin', None)
    
    # نمایش مستقیم منوی ادمین با کیبورد اصلی (i18n)
    db = context.bot_data['database']
    admin_handler = AdminHandlers(db)
    lang = get_user_lang(update, context, db) or 'fa'
    keyboard = admin_handler._get_admin_main_keyboard(update.effective_user.id, lang)
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        t("admin.panel.welcome", lang),
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    # خاتمه ConversationHandler کانال
    return ConversationHandler.END


def get_channel_management_handler():
    """ایجاد ConversationHandler برای مدیریت کانال‌ها"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(channel_management_menu, pattern="^channel_management$"),
            CallbackQueryHandler(channel_management_menu, pattern="^channel_menu$")
        ],
        states={
            CHANNEL_MENU: [
                CallbackQueryHandler(noop_cb, pattern="^noop$"),
                CallbackQueryHandler(handle_page_navigation, pattern="^ch_page_"),
                CallbackQueryHandler(view_channel_details, pattern="^view_channel_"),
                CallbackQueryHandler(toggle_channel_status, pattern="^toggle_channel_"),
                CallbackQueryHandler(show_single_channel_stats, pattern="^channel_stat_"),
                CallbackQueryHandler(test_channel_access, pattern="^test_channel_"),
                CallbackQueryHandler(add_channel_start, pattern="^add_channel$"),
                CallbackQueryHandler(edit_channel_start, pattern="^edit_channel$"),
                CallbackQueryHandler(delete_channel_start, pattern="^delete_channel$"),
                CallbackQueryHandler(reorder_channels_menu, pattern="^reorder_channels$"),
                CallbackQueryHandler(clear_channels, pattern="^clear_channels$"),
                CallbackQueryHandler(clear_channels, pattern="^clear_yes$"),
                CallbackQueryHandler(show_channel_stats, pattern="^channel_stats$"),
                CallbackQueryHandler(show_channel_history, pattern="^channel_history$"),
                # Phase 2 handlers
                CallbackQueryHandler(show_funnel_analysis, pattern="^channel_funnel$"),
                CallbackQueryHandler(show_period_report, pattern="^channel_period_report$"),
                CallbackQueryHandler(export_analytics_csv, pattern="^channel_export_csv$"),
            ],
            REORDER_CHANNELS: [
                CallbackQueryHandler(noop_cb, pattern="^noop$"),
                CallbackQueryHandler(handle_move_channel, pattern="^move_(up|down)_"),
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ],
            ADD_CHANNEL_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_id),
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ],
            ADD_CHANNEL_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_title),
                CallbackQueryHandler(use_default_title, pattern="^use_default_title$"),
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ],
            ADD_CHANNEL_URL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_url),
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ],
            ADD_CHANNEL_CONFIRM: [
                CallbackQueryHandler(save_channel_confirm, pattern="^save_channel$"),
                CallbackQueryHandler(add_channel_start, pattern="^add_channel$"), # Restart
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ],
            EDIT_CHANNEL_SELECT: [
                CallbackQueryHandler(edit_channel_select, pattern="^edit_select_"),
                CallbackQueryHandler(edit_channel_start, pattern="^edit_channel$"),
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ],
            EDIT_CHANNEL_FIELD: [
                CallbackQueryHandler(edit_channel_field, pattern="^edit_field_"),
                CallbackQueryHandler(edit_channel_start, pattern="^edit_channel$"),
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ],
            EDIT_CHANNEL_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_channel_value),
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ],
            DELETE_CHANNEL_CONFIRM: [
                CallbackQueryHandler(delete_channel_confirm, pattern="^del_confirm_"),
                CallbackQueryHandler(delete_channel_execute, pattern="^del_yes$"),
                CallbackQueryHandler(cancel, pattern="^channel_menu$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^channel_menu$"),
            # بازگشت به منوی ادمین و پایان این مکالمه
            CallbackQueryHandler(return_to_admin_menu, pattern="^ch_admin_return$"),
            CommandHandler("cancel", cancel)
        ],
        per_message=False
    )
