"""
Enhanced Validators - مجموعه جامع validatorهای مشترک
این ماژول جایگزین validation logic تکراری در handlers مختلف می‌شود
"""

from typing import Optional, Tuple, Any, List
from dataclasses import dataclass
from pathlib import Path
import re

from config.constants import (
    MAX_ATTACHMENT_CODE_LENGTH, MIN_ATTACHMENT_CODE_LENGTH,
    MAX_ATTACHMENT_NAME_LENGTH, MIN_ATTACHMENT_NAME_LENGTH,
    MAX_COMMENT_LENGTH, MAX_TICKET_SUBJECT_LENGTH, 
    MAX_TICKET_DESCRIPTION_LENGTH, MAX_FAQ_QUESTION_LENGTH,
    MAX_FAQ_ANSWER_LENGTH, MAX_IMAGE_SIZE_BYTES,
    ALLOWED_IMAGE_FORMATS, MAX_VIDEO_SIZE_BYTES,
    ALLOWED_VIDEO_FORMATS, MAX_BROADCAST_MESSAGE_LENGTH
)
from config.config import WEAPON_CATEGORIES, GAME_MODES


@dataclass
class ValidationResult:
    """نتیجه validation با موفقیت و پیام خطا"""
    is_valid: bool
    error_key: Optional[str] = None  # i18n key
    error_details: Optional[dict] = None  # اطلاعات اضافی برای formatting
    
    @property
    def error_message(self) -> str:
        """دریافت کلید i18n برای ترجمه"""
        return self.error_key if self.error_key else ""


class AttachmentValidator:
    """Validators مربوط به اتچمنت‌ها"""
    
    @staticmethod
    def validate_code(code: str) -> ValidationResult:
        """
        اعتبارسنجی کد اتچمنت
        
        Args:
            code: کد اتچمنت
            
        Returns:
            ValidationResult با نتیجه و پیام خطا
            
        Examples:
            >>> AttachmentValidator.validate_code("ABC123").is_valid
            True
            >>> AttachmentValidator.validate_code("AB").is_valid
            False
        """
        if not code or not isinstance(code, str):
            return ValidationResult(False, "validation.attachment.code.required")
        
        code = code.strip()
        
        if len(code) < MIN_ATTACHMENT_CODE_LENGTH:
            return ValidationResult(
                False, 
                "validation.attachment.code.too_short",
                {"min": MIN_ATTACHMENT_CODE_LENGTH}
            )
        
        if len(code) > MAX_ATTACHMENT_CODE_LENGTH:
            return ValidationResult(
                False,
                "validation.attachment.code.too_long",
                {"max": MAX_ATTACHMENT_CODE_LENGTH}
            )
        
        # فقط حروف، اعداد، خط فاصله و underscore
        if not re.match(r'^[A-Za-z0-9_-]+$', code):
            return ValidationResult(
                False,
                "validation.attachment.code.invalid_chars"
            )
        
        return ValidationResult(True)
    
    @staticmethod
    def validate_name(name: str) -> ValidationResult:
        """
        اعتبارسنجی نام اتچمنت
        
        Args:
            name: نام اتچمنت
            
        Returns:
            ValidationResult
        """
        if not name or not isinstance(name, str):
            return ValidationResult(False, "validation.attachment.name.required")
        
        name = name.strip()
        
        if len(name) < MIN_ATTACHMENT_NAME_LENGTH:
            return ValidationResult(
                False,
                "validation.attachment.name.too_short",
                {"min": MIN_ATTACHMENT_NAME_LENGTH}
            )
        
        if len(name) > MAX_ATTACHMENT_NAME_LENGTH:
            return ValidationResult(
                False,
                "validation.attachment.name.too_long",
                {"max": MAX_ATTACHMENT_NAME_LENGTH}
            )
        
        return ValidationResult(True)
    
    @staticmethod
    def validate_image(file_path: Optional[str] = None, 
                      file_size: Optional[int] = None,
                      file_extension: Optional[str] = None) -> ValidationResult:
        """
        اعتبارسنجی فایل تصویر
        
        Args:
            file_path: مسیر فایل (اختیاری)
            file_size: حجم فایل به bytes (اختیاری)
            file_extension: پسوند فایل (اختیاری)
            
        Returns:
            ValidationResult
        """
        # بررسی فرمت
        if file_extension:
            ext = file_extension.lower().lstrip('.')
            if ext not in ALLOWED_IMAGE_FORMATS:
                return ValidationResult(
                    False,
                    "validation.image.invalid_format",
                    {"formats": ", ".join(ALLOWED_IMAGE_FORMATS)}
                )
        
        # بررسی حجم
        if file_size is not None:
            if file_size > MAX_IMAGE_SIZE_BYTES:
                max_mb = MAX_IMAGE_SIZE_BYTES / (1024 * 1024)
                return ValidationResult(
                    False,
                    "validation.image.too_large",
                    {"max_mb": int(max_mb)}
                )
        
        # بررسی وجود فایل
        if file_path:
            path = Path(file_path)
            if not path.exists():
                return ValidationResult(False, "validation.image.not_found")
        
        return ValidationResult(True)


class CategoryValidator:
    """Validators مربوط به دسته‌بندی و سلاح"""
    
    @staticmethod
    def validate_category(category: str) -> ValidationResult:
        """
        اعتبارسنجی دسته‌بندی سلاح
        
        Args:
            category: کلید دسته (مثل 'assault_rifle')
            
        Returns:
            ValidationResult
        """
        if not category:
            return ValidationResult(False, "validation.category.required")
        
        if category not in WEAPON_CATEGORIES:
            return ValidationResult(
                False,
                "validation.category.invalid",
                {"category": category}
            )
        
        return ValidationResult(True)
    
    @staticmethod
    def validate_mode(mode: str) -> ValidationResult:
        """
        اعتبارسنجی حالت بازی (BR/MP)
        
        Args:
            mode: حالت بازی ('br' یا 'mp')
            
        Returns:
            ValidationResult
        """
        if not mode:
            return ValidationResult(False, "validation.mode.required")
        
        if mode not in GAME_MODES:
            return ValidationResult(
                False,
                "validation.mode.invalid",
                {"mode": mode}
            )
        
        return ValidationResult(True)
    
    @staticmethod
    def validate_weapon(weapon: str, category: str, db) -> ValidationResult:
        """
        اعتبارسنجی سلاح در دسته‌بندی
        
        Args:
            weapon: نام سلاح
            category: دسته‌بندی
            db: database adapter
            
        Returns:
            ValidationResult
        """
        if not weapon:
            return ValidationResult(False, "validation.weapon.required")
        
        # بررسی دسته‌بندی
        cat_result = CategoryValidator.validate_category(category)
        if not cat_result.is_valid:
            return cat_result
        
        # بررسی وجود سلاح در دیتابیس
        try:
            weapons = db.get_weapons(category)
            if weapon not in weapons:
                return ValidationResult(
                    False,
                    "validation.weapon.not_found",
                    {"weapon": weapon, "category": category}
                )
        except Exception as e:
            return ValidationResult(
                False,
                "validation.weapon.db_error",
                {"error": str(e)}
            )
        
        return ValidationResult(True)


class TextValidator:
    """Validators مربوط به متن"""
    
    @staticmethod
    def validate_length(text: str, max_length: int, 
                       min_length: int = 1,
                       field_name: str = "text") -> ValidationResult:
        """
        اعتبارسنجی طول متن
        
        Args:
            text: متن ورودی
            max_length: حداکثر طول مجاز
            min_length: حداقل طول مجاز
            field_name: نام فیلد (برای پیام خطا)
            
        Returns:
            ValidationResult
        """
        if not text:
            return ValidationResult(False, f"validation.{field_name}.required")
        
        text = text.strip()
        
        if len(text) < min_length:
            return ValidationResult(
                False,
                f"validation.{field_name}.too_short",
                {"min": min_length}
            )
        
        if len(text) > max_length:
            return ValidationResult(
                False,
                f"validation.{field_name}.too_long",
                {"max": max_length}
            )
        
        return ValidationResult(True)
    
    @staticmethod
    def validate_comment(text: str) -> ValidationResult:
        """اعتبارسنجی نظر کاربر"""
        return TextValidator.validate_length(
            text, MAX_COMMENT_LENGTH, 
            min_length=1, field_name="comment"
        )
    
    @staticmethod
    def validate_ticket_subject(text: str) -> ValidationResult:
        """اعتبارسنجی موضوع تیکت"""
        return TextValidator.validate_length(
            text, MAX_TICKET_SUBJECT_LENGTH,
            min_length=3, field_name="ticket_subject"
        )
    
    @staticmethod
    def validate_ticket_description(text: str) -> ValidationResult:
        """اعتبارسنجی توضیحات تیکت"""
        return TextValidator.validate_length(
            text, MAX_TICKET_DESCRIPTION_LENGTH,
            min_length=10, field_name="ticket_description"
        )
    
    @staticmethod
    def validate_faq_question(text: str) -> ValidationResult:
        """اعتبارسنجی سوال FAQ"""
        return TextValidator.validate_length(
            text, MAX_FAQ_QUESTION_LENGTH,
            min_length=5, field_name="faq_question"
        )
    
    @staticmethod
    def validate_faq_answer(text: str) -> ValidationResult:
        """اعتبارسنجی پاسخ FAQ"""
        return TextValidator.validate_length(
            text, MAX_FAQ_ANSWER_LENGTH,
            min_length=10, field_name="faq_answer"
        )
    
    @staticmethod
    def validate_broadcast_message(text: str) -> ValidationResult:
        """اعتبارسنجی پیام broadcast"""
        return TextValidator.validate_length(
            text, MAX_BROADCAST_MESSAGE_LENGTH,
            min_length=1, field_name="broadcast_message"
        )


class UserValidator:
    """Validators مربوط به کاربر"""
    
    @staticmethod
    def validate_user_id(user_id: Any) -> ValidationResult:
        """
        اعتبارسنجی شناسه کاربر تلگرام
        
        Args:
            user_id: شناسه کاربر
            
        Returns:
            ValidationResult
        """
        if user_id is None:
            return ValidationResult(False, "validation.user_id.required")
        
        try:
            user_id = int(user_id)
            if user_id <= 0:
                return ValidationResult(False, "validation.user_id.invalid")
        except (ValueError, TypeError):
            return ValidationResult(False, "validation.user_id.invalid")
        
        return ValidationResult(True)


# ====================================
# Helper Functions
# ====================================

def validate_all(*results: ValidationResult) -> ValidationResult:
    """
    ترکیب نتایج چند validation
    
    Args:
        *results: ValidationResult های مختلف
        
    Returns:
        اولین ValidationResult که invalid است یا آخرین یکی (valid)
        
    Example:
        >>> code_result = AttachmentValidator.validate_code("ABC")
        >>> name_result = AttachmentValidator.validate_name("My Attachment")
        >>> final = validate_all(code_result, name_result)
    """
    for result in results:
        if not result.is_valid:
            return result
    return ValidationResult(True)


def sanitize_text(text: str, max_length: Optional[int] = None) -> str:
    """
    پاک‌سازی متن ورودی
    
    Args:
        text: متن ورودی
        max_length: حداکثر طول (اختیاری)
        
    Returns:
        متن پاک‌سازی شده
    """
    if not text:
        return ""
    
    # حذف فضاهای اضافی
    text = " ".join(text.split())
    
    # حذف کاراکترهای کنترلی
    text = "".join(char for char in text if char.isprintable() or char in '\n\r\t')
    
    # محدود کردن طول
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    return text.strip()
