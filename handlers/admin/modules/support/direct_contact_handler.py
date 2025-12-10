"""
ماژول مدیریت تماس مستقیم (Direct Contact)
مسئول: تنظیمات تماس مستقیم با پشتیبانی
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import (
    ADMIN_MENU, 
    DIRECT_CONTACT_NAME, 
    DIRECT_CONTACT_LINK
)
from utils.logger import get_logger
from utils.language import get_user_lang
from utils.i18n import t

logger = get_logger('direct_contact', 'admin.log')


class DirectContactHandler(BaseAdminHandler):
    """
    مدیریت تنظیمات تماس مستقیم
    
    Features:
    - فعال/غیرفعال کردن تماس مستقیم
    - تنظیم نام دکمه
    - تنظیم لینک تماس
    - اعتبارسنجی لینک تلگرام
    """
    
    def __init__(self, db):
        """مقداردهی اولیه"""
        super().__init__(db)
        logger.info("DirectContactHandler initialized")
    
    # ==================== Menu Handlers ====================
    
    async def admin_direct_contact_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        منوی مدیریت تماس مستقیم
        
        نمایش:
        - وضعیت فعلی (فعال/غیرفعال)
        - نام دکمه فعلی
        - لینک فعلی
        - دکمه‌های مدیریت
        """
        query = update.callback_query
        if query:
            await query.answer()
        
        # دریافت تنظیمات فعلی
        lang = get_user_lang(update, context, self.db) or 'fa'
        enabled = self.db.get_setting('direct_contact_enabled', 'true')
        contact_name = self.db.get_setting('direct_contact_name', '💬 تماس مستقیم')
        contact_link = self.db.get_setting('direct_contact_link', 'https://t.me/YourSupportChannel')
        
        status_text = t("common.status.enabled", lang) if enabled.lower() == 'true' else t("common.status.disabled", lang)
        
        text = t("admin.direct.menu.text", lang, status=status_text, name=contact_name, link=contact_link)
        
        keyboard = [
            [InlineKeyboardButton(t("admin.direct.buttons.change_name", lang), callback_data="dc_change_name"),
             InlineKeyboardButton(t("admin.direct.buttons.change_link", lang), callback_data="dc_change_link")],
        ]
        
        if enabled.lower() == 'true':
            keyboard.append([InlineKeyboardButton(t("admin.direct.buttons.disable", lang), callback_data="dc_disable")])
        else:
            keyboard.append([InlineKeyboardButton(t("admin.direct.buttons.enable", lang), callback_data="dc_enable")])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_tickets")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        if query:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        logger.info(f"Direct contact menu shown (status={status_text})")
        return ADMIN_MENU
    
    # ==================== Toggle Handlers ====================
    
    async def direct_contact_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        فعال/غیرفعال کردن تماس مستقیم
        
        Callback data format: dc_enable یا dc_disable
        
        Actions:
        - تغییر وضعیت در database
        - نمایش پیام تایید
        - بازگشت به منو
        """
        query = update.callback_query
        await query.answer()
        
        action = query.data.split('_')[-1]  # enable یا disable
        new_status = 'true' if action == 'enable' else 'false'
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        success = self.db.set_setting(
            'direct_contact_enabled', 
            new_status,
            'وضعیت فعال/غیرفعال تماس مستقیم',
            'contact',
            update.effective_user.id
        )
        
        if success:
            status_msg = t("admin.direct.toggled.enabled", lang) if action == 'enable' else t("admin.direct.toggled.disabled", lang)
            await query.answer(status_msg, show_alert=True)
            logger.info(f"Direct contact {action}d by admin {update.effective_user.id}")
        else:
            await query.answer(t("admin.direct.error.toggle", lang), show_alert=True)
            logger.error(f"Failed to toggle direct contact: {action}")
        
        # بازگشت به منوی مدیریت
        return await self.admin_direct_contact_menu(update, context)
    
    # ==================== Change Name Handlers ====================
    
    async def direct_contact_change_name_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        شروع تغییر نام دکمه
        
        Steps:
        1. نمایش نام فعلی
        2. درخواست نام جدید
        3. نمایش راهنما و محدودیت‌ها
        """
        query = update.callback_query
        await query.answer()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        current_name = self.db.get_setting('direct_contact_name', '💬 تماس مستقیم')
        
        text = t("admin.direct.change_name.text", lang, current=current_name)
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="adm_direct_contact")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        logger.info("Waiting for new direct contact name")
        return DIRECT_CONTACT_NAME
    
    async def direct_contact_name_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        دریافت و اعتبارسنجی نام جدید
        
        Validation:
        - حداقل 3 کاراکتر
        - حداکثر 30 کاراکتر
        
        Success:
        - ذخیره در database
        - نمایش پیام موفقیت
        - بازگشت به منو
        """
        lang = get_user_lang(update, context, self.db) or 'fa'
        new_name = update.message.text.strip()
        
        # اعتبارسنجی طول
        if len(new_name) < 3:
            await update.message.reply_text(t("admin.direct.name.too_short", lang))
            return DIRECT_CONTACT_NAME
        
        if len(new_name) > 30:
            await update.message.reply_text(t("admin.direct.name.too_long", lang))
            return DIRECT_CONTACT_NAME
        
        # ذخیره تنظیمات
        success = self.db.set_setting(
            'direct_contact_name', 
            new_name,
            'نام دکمه تماس مستقیم',
            'contact',
            update.effective_user.id
        )
        
        if success:
            await update.message.reply_text(t("admin.direct.name.updated", lang, new=new_name), parse_mode='Markdown')
            logger.info(f"Direct contact name changed to: {new_name}")
        else:
            await update.message.reply_text(t("admin.direct.name.error", lang))
            logger.error("Failed to update direct contact name")
        
        # بازگشت به منوی مدیریت
        return await self.admin_direct_contact_menu(update, context)
    
    # ==================== Change Link Handlers ====================
    
    async def direct_contact_change_link_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        شروع تغییر لینک تماس
        
        Steps:
        1. نمایش لینک فعلی
        2. درخواست لینک جدید
        3. نمایش مثال‌های معتبر
        """
        query = update.callback_query
        await query.answer()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        current_link = self.db.get_setting('direct_contact_link', 'https://t.me/YourSupportChannel')
        
        text = t("admin.direct.change_link.text", lang, current=current_link)
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="adm_direct_contact")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        logger.info("Waiting for new direct contact link")
        return DIRECT_CONTACT_LINK
    
    async def direct_contact_link_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        دریافت و اعتبارسنجی لینک جدید
        
        Validation:
        - باید با https://t.me/ شروع شود
        - حداقل 15 کاراکتر
        
        Success:
        - ذخیره در database
        - نمایش پیام موفقیت
        - بازگشت به منو
        """
        lang = get_user_lang(update, context, self.db) or 'fa'
        new_link = update.message.text.strip()
        
        # اعتبارسنجی لینک تلگرام
        if not new_link.startswith('https://t.me/'):
            await update.message.reply_text(t("admin.direct.link.must_start_tme", lang), parse_mode='Markdown')
            return DIRECT_CONTACT_LINK
        
        if len(new_link) < 15:
            await update.message.reply_text(t("admin.direct.link.too_short", lang))
            return DIRECT_CONTACT_LINK
        
        # ذخیره تنظیمات
        success = self.db.set_setting(
            'direct_contact_link', 
            new_link,
            'لینک تماس مستقیم',
            'contact', 
            update.effective_user.id
        )
        
        if success:
            await update.message.reply_text(t("admin.direct.link.updated", lang, new=new_link), parse_mode='Markdown')
            logger.info(f"Direct contact link changed to: {new_link}")
        else:
            await update.message.reply_text(t("admin.direct.link.error", lang))
            logger.error("Failed to update direct contact link")
        
        # بازگشت به منوی مدیریت
        return await self.admin_direct_contact_menu(update, context)
