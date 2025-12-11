"""
تنظیمات ربات تلگرام CODM Attachments
"""

import os
import sys
from dotenv import load_dotenv
from core.cache.cache_manager import get_cache
# Load environment variables from .env file
load_dotenv()

# i18n
DEFAULT_LANG = os.getenv("DEFAULT_LANG", "fa")
SUPPORTED_LANGS = [s.strip() for s in os.getenv("SUPPORTED_LANGS", "fa,en").split(",") if s.strip()]
FALLBACK_LANG = os.getenv("FALLBACK_LANG", "en")
LANGUAGE_ONBOARDING = os.getenv("LANGUAGE_ONBOARDING", "true").lower() == "true"

# توکن ربات تلگرام - از متغیر محیطی خوانده می‌شود
BOT_TOKEN = os.getenv("BOT_TOKEN")

# بررسی وجود توکن
if not BOT_TOKEN:
    print("❌ خطا: توکن ربات یافت نشد!")
    print("لطفاً فایل .env را ایجاد کرده و BOT_TOKEN را تنظیم کنید.")
    print("می‌توانید از .env.example به عنوان نمونه استفاده کنید.")
    sys.exit(1)

# آیدی ادمین‌های ربات - از متغیر محیطی
# اگر SUPER_ADMIN_ID تنظیم نشده باشد، ربات بدون ادمین شروع می‌شود
admin_id_str = os.getenv("SUPER_ADMIN_ID")
if admin_id_str:
    try:
        default_admin = int(admin_id_str)
        ADMIN_IDS = [default_admin]
    except ValueError:
        print("⚠️ خطا: SUPER_ADMIN_ID باید یک عدد معتبر باشد")
        ADMIN_IDS = []
else:
    print("⚠️ توجه: SUPER_ADMIN_ID تنظیم نشده. ربات بدون ادمین شروع می‌شود.")
    print("برای تنظیم ادمین، فایل .env را ویرایش کنید.")
    ADMIN_IDS = []

# تنظیمات دیتابیس
BACKUP_DIR = "backups"

# دسته‌بندی سلاح‌ها
WEAPON_CATEGORIES = {
    "assault_rifle": "🔫 Assault Rifle",
    "smg": "⚡ SMG",
    "lmg": "🎯 LMG",
    "sniper": "🔭 Sniper Rifle",
    "marksman": "🎪 Marksman Rifle",
    "shotgun": "💥 Shotgun",
    "pistol": "🔫 Pistol",
    "launcher": "🚀 Launcher"
}

# مخفف دسته‌ها برای نمایش فشرده
WEAPON_CATEGORIES_SHORT = {
    "assault_rifle": "🔫 AR",
    "smg": "⚡ SMG",
    "lmg": "🎯 LMG",
    "sniper": "🔭 SR",
    "marksman": "🎪 MR",
    "shotgun": "💥 SG",
    "pistol": "🔫 Pistol",
    "launcher": "🚀 Launcher"
}

# نام‌های فارسی دسته‌ها (برای نمایش به کاربر)
CATEGORIES = {
    "assault_rifle": "تفنگ تهاجمی",
    "smg": "مسلسل کوچک",
    "lmg": "مسلسل سنگین",
    "sniper": "تک‌تیرانداز",
    "marksman": "نشانه‌گیر",
    "shotgun": "ساچمه‌ای",
    "pistol": "تپانچه",
    "launcher": "راکت انداز"
}

# تنظیمات Mode (Battle Royale / Multiplayer)
GAME_MODES = {
    "br": "🪂 BR",
    "mp": "🎮 MP"
}

def build_category_keyboard(categories_dict: dict, callback_prefix: str, show_count: bool = False, db=None, lang: str = 'fa') -> list:
    """
    ساخت کیبورد 2 ستونی برای دسته‌بندی‌ها
    
    Args:
        categories_dict: دیکشنری دسته‌بندی‌ها {key: name}
        callback_prefix: پیشوند callback_data (مثل "cat_", "aac_")
        show_count: نمایش تعداد سلاح‌ها
        db: شیء دیتابیس (فقط برای show_count=True)
        lang: زبان (fa/en) برای translation
    
    Returns:
        لیست ردیف‌های کیبورد
    """
    from telegram import InlineKeyboardButton
    from utils.i18n import t
    
    keyboard = []
    buttons = []
    
    # ✅ بهینه‌سازی: یک query بجای N query + کش 30 دقیقه‌ای
    counts = {}
    if show_count and db:
        try:
            cache = get_cache()
            cache_key = "category_counts"
            cached_counts = cache.get(cache_key)
            if cached_counts is not None:
                counts = cached_counts
            else:
                counts = db.get_all_category_counts()
                cache.set(cache_key, counts, ttl=1800)
        except Exception:
            # در صورت خطا در کش، مستقیم از دیتابیس می‌گیریم
            counts = db.get_all_category_counts()
    
    for key, name in categories_dict.items():
        # استفاده از translation key به جای name مستقیم
        display_name = name
        
        if show_count and db:
            weapons_count = counts.get(key, 0)
            button_text = f"{display_name} ({weapons_count})"
        else:
            button_text = display_name
        
        buttons.append(InlineKeyboardButton(button_text, callback_data=f"{callback_prefix}{key}"))
    
    # تقسیم دکمه‌ها به ردیف‌های 2 تایی
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.append([buttons[i], buttons[i + 1]])
        else:
            keyboard.append([buttons[i]])
    
    return keyboard

def build_weapon_keyboard(weapons: list, callback_prefix: str, category: str = None, add_emoji: bool = False) -> list:
    """
    ساخت کیبورد برای سلاح‌ها با تعداد ستون‌های متغیر بر اساس دسته
    
    Args:
        weapons: لیست نام سلاح‌ها
        callback_prefix: پیشوند callback_data (مثل "wpn_", "aaw_")
        category: دسته سلاح (برای تعیین تعداد ستون‌ها)
        add_emoji: اضافه کردن ایموجی 🔫 به متن دکمه
    
    Returns:
        لیست ردیف‌های کیبورد
    """
    from telegram import InlineKeyboardButton
    
    # تعیین تعداد ستون‌ها بر اساس دسته
    # AR و SMG: 3 ستونی، بقیه: 2 ستونی
    columns = 3 if category in ['assault_rifle', 'smg'] else 2
    
    keyboard = []
    for i in range(0, len(weapons), columns):
        row = []
        for j in range(columns):
            if i + j < len(weapons):
                weapon = weapons[i + j]
                button_text = f"🔫 {weapon}" if add_emoji else weapon
                row.append(InlineKeyboardButton(
                    button_text, 
                    callback_data=f"{callback_prefix}{weapon}"
                ))
        keyboard.append(row)
    
    return keyboard

# وضعیت فعال/غیرفعال بودن هر دسته برای نمایش به کاربران
# ساختار mode-based: {'mp': {'category': {'enabled': bool}}, 'br': {...}}
CATEGORY_SETTINGS = {
    'mp': {
        'assault_rifle': {'enabled': True},
        'launcher': {'enabled': True},
        'lmg': {'enabled': True},
        'marksman': {'enabled': True},
        'pistol': {'enabled': True},
        'shotgun': {'enabled': True},
        'smg': {'enabled': True},
        'sniper': {'enabled': True}
    },
    'br': {
        'assault_rifle': {'enabled': True},
        'launcher': {'enabled': True},
        'lmg': {'enabled': True},
        'marksman': {'enabled': True},
        'pistol': {'enabled': True},
        'shotgun': {'enabled': True},
        'smg': {'enabled': True},
        'sniper': {'enabled': True}
    }
}


# ==================== Helper Functions for Category Settings ====================

def get_category_setting(category: str, mode: str = None) -> dict:
    """
    دریافت تنظیمات یک دسته برای mode مشخص
    
    Args:
        category: کلید دسته (مثل 'assault_rifle')
        mode: مود بازی ('mp' یا 'br') - اگر None باشد، settings برای mp برمی‌گردد
    
    Returns:
        dict: تنظیمات دسته {'enabled': bool}
    """
    if mode is None:
        mode = 'mp'  # default
    
    # بررسی ساختار mode-based
    if isinstance(CATEGORY_SETTINGS, dict) and mode in CATEGORY_SETTINGS:
        # ساختار جدید mode-based
        if category in CATEGORY_SETTINGS[mode]:
            return CATEGORY_SETTINGS[mode][category]
        return {'enabled': True}
    
    # Backward compatibility: ساختار قدیمی global
    if category in CATEGORY_SETTINGS:
        return CATEGORY_SETTINGS[category]
    
    return {'enabled': True}


def is_category_enabled(category: str, mode: str = None) -> bool:
    """
    بررسی فعال بودن یک دسته برای mode مشخص
    
    Args:
        category: کلید دسته
        mode: مود بازی ('mp' یا 'br')
    
    Returns:
        bool: True اگر دسته فعال باشد
    """
    settings = get_category_setting(category, mode)
    return settings.get('enabled', True)


def set_category_enabled(category: str, enabled: bool, mode: str = None):
    """
    تنظیم وضعیت فعال/غیرفعال یک دسته
    
    Args:
        category: کلید دسته
        enabled: وضعیت جدید
        mode: مود بازی ('mp' یا 'br') - None یعنی هر دو mode
    """
    global CATEGORY_SETTINGS
    
    # اگر ساختار mode-based است
    if isinstance(CATEGORY_SETTINGS, dict) and ('mp' in CATEGORY_SETTINGS or 'br' in CATEGORY_SETTINGS):
        if mode is None:
            # تنظیم برای هر دو mode
            for m in ['mp', 'br']:
                if m not in CATEGORY_SETTINGS:
                    CATEGORY_SETTINGS[m] = {}
                if category not in CATEGORY_SETTINGS[m]:
                    CATEGORY_SETTINGS[m][category] = {}
                CATEGORY_SETTINGS[m][category]['enabled'] = enabled
        else:
            # تنظیم برای mode مشخص
            if mode not in CATEGORY_SETTINGS:
                CATEGORY_SETTINGS[mode] = {}
            if category not in CATEGORY_SETTINGS[mode]:
                CATEGORY_SETTINGS[mode][category] = {}
            CATEGORY_SETTINGS[mode][category]['enabled'] = enabled
    else:
        # ساختار قدیمی global
        if category not in CATEGORY_SETTINGS:
            CATEGORY_SETTINGS[category] = {}
        CATEGORY_SETTINGS[category]['enabled'] = enabled
    
    # NOTE: تغییرات فقط در memory اعمال می‌شود
    # برای ذخیره دائمی، باید manually در این فایل ذخیره شود


# NOTE: save_category_settings() removed - was causing file corruption
# CATEGORY_SETTINGS is now manually managed in this file
# Changes are applied in-memory and persist across bot restarts via database

# تنظیمات فعال/غیرفعال بودن سلاح‌ها
# کلید: "category__weapon" (مثلاً "assault_rifle__AK47")
# مقدار: {"enabled": True/False}
WEAPON_SETTINGS = {}

# تنظیمات نوتیفیکیشن خودکار و قالب پیام‌ها
# placeholders مجاز: {category} {category_name} {weapon} {code} {name} {old_name} {new_name} {old_code} {new_code}
NOTIFICATION_SETTINGS = {
    "enabled": True,
    "events": {
        "add_attachment": True,
        "edit_name": True,
        "edit_image": True,
        "edit_code": True,
        "delete_attachment": True,
        "top_set": True,
        "top_added": True,
        "top_removed": True
    },
    "templates": {
        "add_attachment": "notification.template.add_attachment",
        "edit_name": "notification.template.edit_name",
        "edit_image": "notification.template.edit_image",
        "edit_code": "notification.template.edit_code",
        "delete_attachment": "notification.template.delete_attachment",
        "top_set": "notification.template.top_set",
        "top_added": "notification.template.top_added",
        "top_removed": "notification.template.top_removed"
    },
    "auto_notify": True
}

# پیام‌های ربات
MESSAGES = {
    "welcome": """
🎮 **به ربات CODM Attachments خوش آمدید!**

این ربات برای مشاهده بهترین اتچمنت‌های سلاح‌های Call of Duty Mobile طراحی شده.

🔹 از منوی زیر گزینه مورد نظر خود را انتخاب کنید:
""",
    "select_category": "📂 **دسته سلاح مورد نظر را انتخاب کنید:**",
    "select_weapon": "🔫 **سلاح مورد نظر را انتخاب کنید:**",
    "no_weapons": "❌ هنوز سلاحی در این دسته اضافه نشده است.",
    "no_attachments": "❌ هنوز اتچمنتی برای این سلاح اضافه نشده است.",
    "top_attachments": "⭐ **5 اتچمنت برتر برای {weapon}:**",
    "all_attachments": "📋 **تمام اتچمنت‌های {weapon}:**",
    "search_prompt": "🔍 **نام سلاح یا کد اتچمنت را وارد کنید:**",
    "search_no_results": "❌ نتیجه‌ای یافت نشد.",
    "help_text": """
📖 **راهنمای ربات**

🔫 **دریافت اتچمنت:** دسته → سلاح → مود (BR/MP) → برترها یا همه

💡 **پیشنهادی:** بهترین ترکیب‌های انتخاب شده برای هر سلاح

⭐ **برترها:** اتچمنت‌های برتر فصل با عکس و کد

⚙️ **تنظیمات:** HUD، Basic و Sensitivity جداگانه برای BR/MP

🔍 **جستجو:** نام سلاح یا کد اتچمنت را تایپ کنید

📞 **پشتیبانی:** ثبت تیکت، FAQ و بازخورد

━━━━━━━━━━━━━━

💡 **نکته:** کدها را در بازی جستجو کنید. BR و MP متفاوت هستند.

🎮 **موفق باشید!**
""",
    "admin_welcome": """
👨‍💼 **پنل مدیریت ادمین**

از منوی زیر گزینه مورد نظر را انتخاب کنید:
""",
    "not_admin": "❌ شما دسترسی ادمین ندارید.",
    "backup_created": "✅ بکاپ با موفقیت ایجاد شد: {filename}",
    "data_saved": "✅ اطلاعات با موفقیت ذخیره شد.",
    "attachment_added": "✅ اتچمنت جدید اضافه شد.",
    "attachment_deleted": "✅ اتچمنت حذف شد.",
    "weapon_added": "✅ سلاح جدید اضافه شد.",
    "weapon_deleted": "✅ سلاح حذف شد.",
}

# تنظیمات صفحه‌بندی
ITEMS_PER_PAGE = 10

# تنظیمات لاگ
LOG_FILE = "bot.log"
LOG_LEVEL = "INFO"
