"""
ماژول مدیریت تماس مستقیم برای پنل ادمین
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes


class DirectContactHandlers:
    """کلاس handlers مدیریت تماس مستقیم"""
    
    def __init__(self, db, role_manager):
        self.db = db
        self.role_manager = role_manager
    
    async def admin_direct_contact_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی مدیریت تماس مستقیم"""
        query = update.callback_query
        await query.answer()
        
        # دریافت تنظیمات فعلی
        enabled = self.db.get_setting('direct_contact_enabled', 'true')
        contact_name = self.db.get_setting('direct_contact_name', '💬 تماس مستقیم')
        contact_link = self.db.get_setting('direct_contact_link', 'https://t.me/YourSupportChannel')
        
        status_text = "🟢 فعال" if enabled.lower() == 'true' else "🔴 غیرفعال"
        
        text = f"""💬 **مدیریت تماس مستقیم**

📊 **وضعیت فعلی:**
├─ وضعیت: {status_text}
├─ نام دکمه: {contact_name}
└─ لینک: `{contact_link}`

این قسمت به کاربران امکان دسترسی مستقیم به کانال/اکانت پشتیبانی شما را می‌دهد."""
        
        keyboard = [
            [InlineKeyboardButton("📝 تغییر نام دکمه", callback_data="dc_change_name"),
             InlineKeyboardButton("🔗 تغییر لینک", callback_data="dc_change_link")],
        ]
        
        if enabled.lower() == 'true':
            keyboard.append([InlineKeyboardButton("🔴 غیرفعال کردن", callback_data="dc_disable")])
        else:
            keyboard.append([InlineKeyboardButton("🟢 فعال کردن", callback_data="dc_enable")])
        
        keyboard.append([InlineKeyboardButton("⬅️ بازگشت", callback_data="admin_tickets")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return 0  # ADMIN_MENU
    
    async def direct_contact_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """فعال/غیرفعال کردن تماس مستقیم"""
        query = update.callback_query
        await query.answer()
        
        action = query.data.split('_')[-1]  # enable یا disable
        new_status = 'true' if action == 'enable' else 'false'
        
        success = self.db.set_setting(
            'direct_contact_enabled', 
            new_status,
            'وضعیت فعال/غیرفعال تماس مستقیم',
            'contact',
            update.effective_user.id
        )
        
        if success:
            status_text = "فعال" if action == 'enable' else "غیرفعال"
            await query.answer(f"✅ تماس مستقیم {status_text} شد", show_alert=True)
        else:
            await query.answer("❌ خطا در تغییر وضعیت", show_alert=True)
        
        # بازگشت به منوی مدیریت
        return await self.admin_direct_contact_menu(update, context)
    
    async def direct_contact_change_name_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع تغییر نام دکمه"""
        query = update.callback_query
        await query.answer()
        
        current_name = self.db.get_setting('direct_contact_name', '💬 تماس مستقیم')
        
        text = f"""📝 **تغییر نام دکمه تماس مستقیم**

نام فعلی: `{current_name}`

لطفاً نام جدید برای دکمه تماس مستقیم را وارد کنید:

**نکته:** می‌تونید از emoji استفاده کنید (مثل 💬 یا 📞)"""
        
        keyboard = [[InlineKeyboardButton("❌ لغو", callback_data="adm_direct_contact")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return 54  # DIRECT_CONTACT_NAME
    
    async def direct_contact_name_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت نام جدید"""
        new_name = update.message.text.strip()
        
        if len(new_name) < 3:
            await update.message.reply_text("❌ نام دکمه باید حداقل 3 کاراکتر باشد.")
            return 54  # DIRECT_CONTACT_NAME
        
        if len(new_name) > 30:
            await update.message.reply_text("❌ نام دکمه نباید بیش از 30 کاراکتر باشد.")
            return 54  # DIRECT_CONTACT_NAME
        
        success = self.db.set_setting(
            'direct_contact_name', 
            new_name,
            'نام دکمه تماس مستقیم',
            'contact',
            update.effective_user.id
        )
        
        if success:
            await update.message.reply_text(f"✅ نام دکمه به `{new_name}` تغییر یافت.", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ خطا در تغییر نام")
        
        # بازگشت به منوی مدیریت
        # ایجاد یک callback query fake برای استفاده از admin_direct_contact_menu
        context.user_data['fake_callback'] = True
        return 0  # ADMIN_MENU
    
    async def direct_contact_change_link_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع تغییر لینک"""
        query = update.callback_query
        await query.answer()
        
        current_link = self.db.get_setting('direct_contact_link', 'https://t.me/YourSupportChannel')
        
        text = f"""🔗 **تغییر لینک تماس مستقیم**

لینک فعلی: `{current_link}`

لطفاً لینک جدید را وارد کنید:

**مثال‌های معتبر:**
• `https://t.me/YourChannel`
• `https://t.me/YourBot`
• `https://t.me/+ABC123xyz`

**نکته:** لینک باید با https://t.me/ شروع شود."""
        
        keyboard = [[InlineKeyboardButton("❌ لغو", callback_data="adm_direct_contact")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return 55  # DIRECT_CONTACT_LINK
    
    async def direct_contact_link_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت لینک جدید"""
        new_link = update.message.text.strip()
        
        # اعتبارسنجی لینک تلگرام
        if not new_link.startswith('https://t.me/'):
            await update.message.reply_text("❌ لینک باید با `https://t.me/` شروع شود.")
            return 55  # DIRECT_CONTACT_LINK
        
        if len(new_link) < 15:
            await update.message.reply_text("❌ لینک خیلی کوتاه است.")
            return 55  # DIRECT_CONTACT_LINK
        
        success = self.db.set_setting(
            'direct_contact_link', 
            new_link,
            'لینک تماس مستقیم',
            'contact', 
            update.effective_user.id
        )
        
        if success:
            await update.message.reply_text(f"✅ لینک تماس مستقیم به `{new_link}` تغییر یافت.", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ خطا در تغییر لینک")
        
        # بازگشت به منوی مدیریت
        context.user_data['fake_callback'] = True
        return 0  # ADMIN_MENU
