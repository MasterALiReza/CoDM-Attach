"""
Manage Handler - مدیریت پیشرفته اتچمنت‌های کاربران (جستجو، حذف، و ...)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from core.database.database_adapter import get_database_adapter
from utils.logger import get_logger
from utils.i18n import t
from utils.language import get_user_lang
from .review_handler import check_ua_admin_permission, show_ua_admin_menu
import time

logger = get_logger('ua_admin_manage', 'admin.log')
db = get_database_adapter()

# States
WAIT_SEARCH_INPUT = 1

async def show_manage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی مدیریت اتچمنت‌ها"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    lang = get_user_lang(update, context, db) or 'fa'
    
    if not check_ua_admin_permission(user_id):
        await query.answer(t('error.unauthorized', lang), show_alert=True)
        return

    keyboard = [
        [InlineKeyboardButton(t("admin.ua.manage.search_user", lang), callback_data="ua_manage_search")],
        [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_admin_menu")]
    ]
    
    message = t("admin.ua.manage.menu_title", lang)
    
    try:
        await query.edit_message_text(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception:
        await update.effective_chat.send_message(
            message,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def start_search_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع جستجوی کاربر"""
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(update, context, db) or 'fa'
    
    await query.message.reply_text(
        t("admin.ua.manage.search_prompt", lang),
        reply_markup=ReplyKeyboardRemove()
    )
    return WAIT_SEARCH_INPUT

async def receive_search_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت ورودی جستجو (نام کاربری یا آیدی)"""
    input_text = update.message.text.strip()
    lang = get_user_lang(update, context, db) or 'fa'
    
    # تمیز کردن ورودی (@ را حذف کن)
    search_term = input_text.replace("@", "")
    
    user = None
    
    # 1. تلاش برای پیدا کردن با ID
    if search_term.isdigit():
        user = db.get_user(int(search_term))
    
    # 2. اگر نبود، پیدا کردن با username
    if not user:
        # متد get_user_by_username وجود نداره، باید کوئری بزنیم یا اضافه کنیم
        # فرض می‌کنیم متد get_user_by_username را بعدا اضافه میکنیم یا اینجا کوئری مستقیم میزنیم
        # فعلا از طریق SQL
        try:
            with db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM users WHERE username ILIKE %s", (search_term,))
                user = cur.fetchone()
        except Exception as e:
            logger.error(f"Search error: {e}")
    
    if not user:
        await update.message.reply_text(
            t("error.user_not_found", lang),
            reply_markup=InlineKeyboardMarkup([[
                 InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_admin_manage")
            ]])
        )
        return ConversationHandler.END
    
    # کاربر پیدا شد، نمایش لیست اتچمنت‌ها
    context.user_data['manage_target_user_id'] = user['user_id']
    await show_user_attachments_list(update, context, user['user_id'])
    return ConversationHandler.END

async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو جستجو"""
    lang = get_user_lang(update, context, db) or 'fa'
    await update.message.reply_text(t("common.cancelled", lang))
    return ConversationHandler.END

async def show_user_attachments_list(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None):
    """نمایش لیست اتچمنت‌های یک کاربر"""
    # ساپورت هم برای message و هم callback_query
    query = update.callback_query
    if query:
        await query.answer()
        message_func = query.edit_message_text
    else:
        message_func = update.message.reply_text
        
    lang = get_user_lang(update, context, db) or 'fa'
    
    # اگر page در callback بود
    page = 0
    if query and 'ua_manage_list_' in query.data:
        parts = query.data.split('_')
        # ua_manage_list_USERID_PAGE
        if len(parts) >= 5:
            user_id = int(parts[3])
            page = int(parts[4])
    else:
        # اولین بار
        if not user_id:
             user_id = context.user_data.get('manage_target_user_id')
    
    if not user_id:
        await message_func(t("error.generic", lang))
        return

    # دریافت لیست
    PER_PAGE = 10
    offset = page * PER_PAGE
    
    # کوئری مستقیم چون get_user_attachments_by_user_id نداریم
    try:
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM user_attachments 
                WHERE user_id = %s 
                ORDER BY created_at DESC 
                LIMIT %s OFFSET %s
            """, (user_id, PER_PAGE, offset))
            attachments = cur.fetchall()
            
            # تعداد کل
            cur.execute("SELECT COUNT(*) as cnt FROM user_attachments WHERE user_id = %s", (user_id,))
            total = cur.fetchone()['cnt']
    except Exception as e:
        logger.error(f"List fetch error: {e}")
        attachments = []
        total = 0
        
    if not attachments and page == 0:
        if query:
            # اگر از قبل پیامی هست
            try:
                await query.edit_message_text(
                    t("admin.ua.manage.no_attachments", lang),
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_admin_manage")]])
                )
            except:
                await update.effective_chat.send_message(t("admin.ua.manage.no_attachments", lang))
        else:
            await update.message.reply_text(
                t("admin.ua.manage.no_attachments", lang),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_admin_manage")]])
            )
        return

    total_pages = (total - 1) // PER_PAGE + 1
    
    text = t("admin.ua.manage.list_title", lang, user_id=user_id, total=total) + "\n\n"
    
    keyboard = []
    for att in attachments:
        status_icon = "⏳" if att['status'] == 'pending' else ("✅" if att['status'] == 'approved' else "❌")
        name = att.get('custom_weapon_name') or att.get('weapon_name') or "Unknown"
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {name} ({att['id']})",
                callback_data=f"ua_manage_view_{att['id']}"
            )
        ])
        
    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"ua_manage_list_{user_id}_{page-1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"ua_manage_list_{user_id}_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
        
    keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="ua_admin_manage")])
    
    if query:
        try:
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        except:
             # اگر عکس بود
            await query.message.delete()
            await update.effective_chat.send_message(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def view_attachment_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشاهده و مدیریت تکی"""
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(update, context, db) or 'fa'
    
    att_id = int(query.data.replace("ua_manage_view_", ""))
    attachment = db.get_user_attachment(att_id)
    
    if not attachment:
        await query.answer(t("attachment.not_found", lang), show_alert=True)
        return

    # نمایش مثل review handler اما با دکمه Delete
    caption = (
        f"📎 ID: `{attachment['id']}`\n"
        f"👤 User: `{attachment['user_id']}`\n"
        f"🔫 Weapon: {attachment.get('custom_weapon_name') or attachment.get('weapon_name')}\n"
        f"📊 Status: {attachment['status']}\n"
        f"📅 Date: {attachment['created_at']}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(t("menu.buttons.delete", lang) + " 🗑️", callback_data=f"ua_manage_ask_del_{att_id}")],
        [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"ua_manage_list_{attachment['user_id']}_0")]
    ]
    
    await query.message.delete() # حذف لیست قبلی
    await update.effective_chat.send_photo(
        photo=attachment['image_file_id'],
        caption=caption,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def ask_delete_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید حذف در مدیریت"""
    query = update.callback_query
    await query.answer()
    lang = get_user_lang(update, context, db) or 'fa'
    
    att_id = int(query.data.replace('ua_manage_ask_del_', ''))
    
    keyboard = [
        [
            InlineKeyboardButton(t("common.yes", lang), callback_data=f"ua_manage_do_del_{att_id}"),
            InlineKeyboardButton(t("common.no", lang), callback_data=f"ua_manage_view_{att_id}") # برگرد به ویو، ولی ویو عکس میخواد...
            # اینجا چون عکس قبلا ارسال شده، شاید بهتره فقط کیبورد ادیت بشه
        ]
    ]
    
    await query.edit_message_caption(
        caption=query.message.caption + "\n\n⚠️ " + t("ua.my.delete_confirm", lang),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def perform_delete_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انجام حذف"""
    query = update.callback_query
    # await query.answer() # answer after logic
    lang = get_user_lang(update, context, db) or 'fa'
    
    att_id = int(query.data.replace('ua_manage_do_del_', ''))
    
    # دریافت user_id قبل از حذف برای بازگشت به لیست
    att = db.get_user_attachment(att_id)
    user_id = att['user_id'] if att else None
    
    if db.delete_user_attachment(att_id):
        await query.answer(t("ua.success.deleted", lang), show_alert=True)
        await query.message.delete()
        
        # بازگشت به لیست
        if user_id:
            # ساخت آبجکت فیک برای فراخوانی تابع
            context.user_data['manage_target_user_id'] = user_id
            # اینجا چون show_user_attachments_list هم با مسیج و هم کوئری کار میکنه،
            # اما ما الان کوئری فعلی مون مال دکمه حذف بود که پاک شده
            # پس یک پیام جدید می فرستیم
            await show_user_attachments_list(update, context, user_id)
    else:
        await query.answer(t("error.generic", lang), show_alert=True)


search_users_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_search_user, pattern="^ua_manage_search$")],
    states={
        WAIT_SEARCH_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_search_input)]
    },
    fallbacks=[MessageHandler(filters.Regex("^/cancel$"), cancel_search)],
    name="ua_manage_search",
    persistent=False
)

manage_handlers = [
    CallbackQueryHandler(show_manage_menu, pattern="^ua_admin_manage$"),
    search_users_conv,
    CallbackQueryHandler(show_user_attachments_list, pattern="^ua_manage_list_"),
    CallbackQueryHandler(view_attachment_manage, pattern="^ua_manage_view_"),
    CallbackQueryHandler(ask_delete_manage, pattern="^ua_manage_ask_del_"),
    CallbackQueryHandler(perform_delete_manage, pattern="^ua_manage_do_del_"),
]
