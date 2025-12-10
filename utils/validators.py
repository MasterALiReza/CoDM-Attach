"""
سیستم validation ورودی‌ها برای جلوگیری از injection و خطاها
"""

import re
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# محدودیت‌های طول
MAX_WEAPON_NAME = 50
MAX_ATTACHMENT_NAME = 100
MAX_ATTACHMENT_CODE = 20
MAX_CHANNEL_TITLE = 100
MAX_MESSAGE_LENGTH = 4096  # محدودیت تلگرام
MAX_CAPTION_LENGTH = 1024
MAX_CALLBACK_DATA = 64

# Patterns مجاز
WEAPON_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9\-_\s\u0600-\u06FF]+$')  # حروف، اعداد، فاصله، فارسی
ATTACHMENT_CODE_PATTERN = re.compile(r'^[A-Z0-9\-]+$')  # فقط حروف بزرگ، اعداد و خط تیره
# فرمت دقیق‌تر برای channel ID
CHANNEL_USERNAME_PATTERN = re.compile(r'^@[a-zA-Z][a-zA-Z0-9_]{4,31}$')  # @username (5-32 chars)
CHANNEL_NUMERIC_ID_PATTERN = re.compile(r'^-100\d{10}$')  # -100xxxxxxxxxx (13 digits total)
FILE_ID_PATTERN = re.compile(r'^[A-Za-z0-9_\-]{20,}$')  # Telegram file ID


def sanitize_text(text: str, max_length: int = None) -> str:
    """پاکسازی متن از کاراکترهای خطرناک"""
    if not text:
        return ""
    
    # حذف کاراکترهای کنترلی
    text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')
    
    # حذف HTML/Markdown injection
    dangerous_chars = ['<', '>', '&', '"', "'", '`', '*', '_', '[', ']', '(', ')']
    for char in dangerous_chars:
        text = text.replace(char, '')
    
    # محدود کردن طول
    if max_length:
        text = text[:max_length]
    
    return text.strip()


def validate_weapon_name(name: str) -> Tuple[bool, Optional[str]]:
    """اعتبارسنجی نام سلاح"""
    if not name:
        return False, "نام سلاح نمی‌تواند خالی باشد"
    
    name = name.strip()
    
    if len(name) > MAX_WEAPON_NAME:
        return False, f"نام سلاح باید کمتر از {MAX_WEAPON_NAME} کاراکتر باشد"
    
    if not WEAPON_NAME_PATTERN.match(name):
        return False, "نام سلاح فقط می‌تواند شامل حروف، اعداد، فاصله و خط تیره باشد"
    
    return True, name


def validate_attachment_name(name: str) -> Tuple[bool, Optional[str]]:
    """اعتبارسنجی نام اتچمنت"""
    if not name:
        return False, "نام اتچمنت نمی‌تواند خالی باشد"
    
    name = name.strip()
    
    if len(name) > MAX_ATTACHMENT_NAME:
        return False, f"نام اتچمنت باید کمتر از {MAX_ATTACHMENT_NAME} کاراکتر باشد"
    
    # اتچمنت می‌تواند کاراکترهای بیشتری داشته باشد
    return True, name


def validate_attachment_code(code: str) -> Tuple[bool, Optional[str]]:
    """اعتبارسنجی کد اتچمنت"""
    if not code:
        return False, "کد اتچمنت نمی‌تواند خالی باشد"
    
    code = code.strip().upper()
    
    if len(code) > MAX_ATTACHMENT_CODE:
        return False, f"کد اتچمنت باید کمتر از {MAX_ATTACHMENT_CODE} کاراکتر باشد"
    
    if not ATTACHMENT_CODE_PATTERN.match(code):
        return False, "کد اتچمنت فقط می‌تواند شامل حروف بزرگ انگلیسی، اعداد و خط تیره باشد"
    
    return True, code


def validate_channel_id(channel_id: str) -> Tuple[bool, Optional[str]]:
    """
    اعتبارسنجی دقیق شناسه کانال تلگرام
    
    فرمت‌های معتبر:
    - @username: حروف انگلیسی، اعداد، underscore (5-32 کاراکتر)
    - -100xxxxxxxxxx: عدد منفی 13 رقمی که با -100 شروع می‌شود
    """
    if not channel_id:
        return False, "شناسه کانال نمی‌تواند خالی باشد"
    
    channel_id = channel_id.strip()
    
    # بررسی فرمت @username
    if channel_id.startswith('@'):
        if CHANNEL_USERNAME_PATTERN.match(channel_id):
            return True, channel_id
        else:
            return False, (
                "فرمت username نامعتبر است.\n"
                "• باید با @ شروع شود\n"
                "• حداقل 5 و حداکثر 32 کاراکتر\n"
                "• فقط حروف انگلیسی، اعداد و underscore (_)\n"
                "مثال: @mychannel"
            )
    
    # بررسی فرمت عددی (برای supergroups/channels)
    if channel_id.startswith('-'):
        if CHANNEL_NUMERIC_ID_PATTERN.match(channel_id):
            return True, channel_id
        else:
            return False, (
                "فرمت شناسه عددی نامعتبر است.\n"
                "• باید 13 رقم باشد و با -100 شروع شود\n"
                "مثال: -1001234567890"
            )
    
    # اگر هیچکدام نبود
    return False, (
        "شناسه کانال نامعتبر است.\n"
        "فرمت‌های معتبر:\n"
        "• @username (برای کانال‌های عمومی)\n"
        "• -1001234567890 (شناسه عددی)"
    )


def validate_channel_url(url: str) -> Tuple[bool, Optional[str]]:
    """اعتبارسنجی URL کانال"""
    if not url:
        return False, "لینک کانال نمی‌تواند خالی باشد"
    
    url = url.strip()
    
    # باید با t.me یا telegram.me شروع شود
    if not (url.startswith('https://t.me/') or url.startswith('https://telegram.me/')):
        return False, "لینک باید با https://t.me/ یا https://telegram.me/ شروع شود"
    
    return True, url


def validate_file_id(file_id: str) -> Tuple[bool, Optional[str]]:
    """اعتبارسنجی Telegram file ID"""
    if not file_id:
        return True, None  # File ID اختیاری است
    
    file_id = file_id.strip()
    
    if not FILE_ID_PATTERN.match(file_id):
        return False, "فایل آپلود شده معتبر نیست"
    
    return True, file_id


def validate_message_text(text: str) -> Tuple[bool, Optional[str]]:
    """اعتبارسنجی متن پیام"""
    if not text:
        return False, "متن پیام نمی‌تواند خالی باشد"
    
    text = text.strip()
    
    if len(text) > MAX_MESSAGE_LENGTH:
        return False, f"متن پیام باید کمتر از {MAX_MESSAGE_LENGTH} کاراکتر باشد"
    
    return True, text


def validate_category(category: str, valid_categories: list) -> Tuple[bool, Optional[str]]:
    """اعتبارسنجی دسته‌بندی"""
    if not category:
        return False, "دسته‌بندی انتخاب نشده"
    
    if category not in valid_categories:
        return False, "دسته‌بندی نامعتبر است"
    
    return True, category


def validate_mode(mode: str) -> Tuple[bool, Optional[str]]:
    """اعتبارسنجی mode (BR/MP)"""
    if not mode:
        return False, "حالت بازی انتخاب نشده"
    
    if mode not in ['br', 'mp']:
        return False, "حالت بازی باید br یا mp باشد"
    
    return True, mode


def validate_admin_id(admin_id: str) -> Tuple[bool, Optional[int]]:
    """اعتبارسنجی آیدی ادمین"""
    try:
        admin_id = int(admin_id.strip())
        
        if admin_id <= 0:
            return False, "آیدی ادمین باید عدد مثبت باشد"
        
        return True, admin_id
        
    except ValueError:
        return False, "آیدی ادمین باید عدد باشد"


def validate_callback_data(data: str) -> bool:
    """بررسی طول callback_data"""
    if not data:
        return True
    
    if len(data) > MAX_CALLBACK_DATA:
        logger.warning(f"Callback data too long: {len(data)} chars")
        return False
    
    return True


def escape_markdown(text: str) -> str:
    """Escape کردن کاراکترهای Markdown"""
    if not text:
        return ""
    
    # کاراکترهایی که باید escape شوند در MarkdownV1
    escape_chars = ['*', '_', '`', '[']
    
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


def escape_html(text: str) -> str:
    """Escape کردن کاراکترهای HTML"""
    if not text:
        return ""
    
    # مهم: & باید اول escape شود تا دوبار escape نشود
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&#39;')
    
    return text


def truncate_text(text: str, max_length: int, suffix: str = "...") -> str:
    """کوتاه کردن متن با حفظ معنا"""
    if not text or len(text) <= max_length:
        return text
    
    # پیدا کردن آخرین فاصله قبل از حد مجاز
    truncated = text[:max_length - len(suffix)]
    last_space = truncated.rfind(' ')
    
    if last_space > 0:
        truncated = truncated[:last_space]
    
    return truncated + suffix


def is_valid_image_url(url: str) -> bool:
    """بررسی معتبر بودن URL تصویر"""
    if not url:
        return False
    
    url = url.lower()
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    
    return any(url.endswith(ext) for ext in valid_extensions)


def normalize_weapon_name(name: str) -> str:
    """نرمال‌سازی نام سلاح برای جستجو"""
    if not name:
        return ""
    
    # تبدیل به حروف کوچک
    name = name.lower()
    
    # حذف فاصله‌های اضافی
    name = ' '.join(name.split())
    
    # حذف کاراکترهای خاص
    name = re.sub(r'[^\w\s\u0600-\u06FF]', '', name)
    
    return name.strip()
