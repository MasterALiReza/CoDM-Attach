"""
Content Validator - فیلترینگ و اعتبارسنجی محتوای کاربران
"""

import re
from typing import Tuple, Optional, Dict
from utils.logger import get_logger

logger = get_logger('content_validator', 'user.log')


class ContentValidator:
    """اعتبارسنجی و فیلترینگ محتوای ارسالی کاربران"""
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseAdapter instance
        """
        self.db = db
        self.blacklist_cache = {}
        self._load_blacklist()
    
    def _load_blacklist(self):
        """بارگذاری کلمات ممنوعه از دیتابیس"""
        try:
            words = self.db.get_all_blacklisted_words()
            cache = {}
            for word in words or []:
                w = (word or {}).get('word')
                if not w:
                    continue
                cache[w] = {
                    'category': (word or {}).get('category') or 'general',
                    'severity': int(((word or {}).get('severity') or 1))
                }
            self.blacklist_cache = cache
            logger.info(f"Loaded {len(self.blacklist_cache)} blacklisted words")
        except Exception as e:
            logger.error(f"Error loading blacklist: {e}")
            self.blacklist_cache = {}
    
    def reload_blacklist(self):
        """بارگذاری مجدد blacklist (برای وقتی ادمین کلمه جدید اضافه می‌کنه)"""
        self._load_blacklist()
    
    def normalize_text(self, text: str) -> str:
        """
        نرمال‌سازی متن برای بررسی
        
        - حذف فاصله‌ها و ZWNJ
        - تبدیل اعداد فارسی/عربی به انگلیسی
        - حذف حروف تکراری بیش از 2 بار
        - تبدیل به lowercase
        - نرمال‌سازی حروف مشابه
        """
        if not text:
            return ""
        
        # 1. حذف whitespace و zero-width characters
        text = text.replace(' ', '').replace('\u200c', '').replace('\u200b', '')
        text = text.replace('\t', '').replace('\n', '')
        
        # 2. تبدیل اعداد فارسی/عربی
        persian_nums = '۰۱۲۳۴۵۶۷۸۹'
        arabic_nums = '٠١٢٣٤٥٦٧٨٩'
        trans_table = str.maketrans(
            persian_nums + arabic_nums,
            '0123456789' * 2
        )
        text = text.translate(trans_table)
        
        # 3. حذف حروف تکراری (بیش از 2)
        text = re.sub(r'(.)\1{2,}', r'\1\1', text)
        
        # 4. حذف emoji و نمادها
        text = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
        
        # 5. تبدیل به lowercase
        text = text.lower().strip()
        
        # 6. نرمال‌سازی حروف فارسی مشابه
        text = text.replace('ك', 'ک').replace('ي', 'ی')
        text = text.replace('ة', 'ه')
        
        return text
    
    def check_blacklisted_words(self, text: str) -> Optional[Dict]:
        """
        بررسی وجود کلمات ممنوعه در متن
        
        Returns:
            Dict با اطلاعات تخلف یا None
        """
        normalized = self.normalize_text(text)
        
        for word, info in self.blacklist_cache.items():
            # نرمال‌سازی کلمه blacklist هم
            normalized_word = self.normalize_text(word)
            
            if normalized_word in normalized:
                logger.warning(
                    f"Blacklisted word detected: '{word}' "
                    f"(category: {info['category']}, severity: {info['severity']})"
                )
                return {
                    'word': word,
                    'category': info['category'],
                    'severity': info['severity'],
                    'original_text': text
                }
        
        return None
    
    def validate_length(self, text: str, max_length: int) -> Tuple[bool, str]:
        """
        بررسی طول متن
        
        Returns:
            (is_valid, reason)
        """
        if not text or len(text.strip()) == 0:
            return False, "متن خالی است"
        
        if len(text) > max_length:
            return False, f"متن بیش از {max_length} کاراکتر است ({len(text)} کاراکتر)"
        
        return True, "OK"
    
    def check_spam_patterns(self, text: str) -> bool:
        """
        بررسی الگوهای spam
        
        Returns:
            True اگر spam باشد
        """
        spam_patterns = [
            r't\.me/',  # لینک تلگرام
            r'@\w+',  # منشن کانال
            r'http[s]?://',  # لینک
            r'کانال',
            r'عضو\s*شو',
            r'join',
            r'تبلیغ',
        ]
        
        text_lower = text.lower()
        for pattern in spam_patterns:
            if re.search(pattern, text_lower):
                logger.warning(f"Spam pattern detected: {pattern}")
                return True
        
        return False
    
    def validate_text(
        self, 
        text: str, 
        max_length: int = 100,
        check_spam: bool = True
    ) -> Tuple[bool, str, Optional[Dict]]:
        """
        اعتبارسنجی کامل متن
        
        Args:
            text: متن برای بررسی
            max_length: حداکثر طول مجاز
            check_spam: بررسی spam patterns
        
        Returns:
            (is_valid, reason, violation_info)
            violation_info فقط در صورت تخلف دارد مقدار
        """
        # 1. بررسی طول
        valid, reason = self.validate_length(text, max_length)
        if not valid:
            return False, reason, None
        
        # 2. بررسی کلمات ممنوعه
        violation = self.check_blacklisted_words(text)
        if violation:
            severity = violation['severity']
            if severity == 3:
                reason = "⚠️ استفاده از کلمات رکیک شدید - تخلف ثبت شد"
            elif severity == 2:
                reason = "⚠️ استفاده از کلمات نامناسب - اخطار"
            else:
                reason = "⚠️ لطفا از کلمات مناسب استفاده کنید"
            
            return False, reason, violation
        
        # 3. بررسی spam
        if check_spam and self.check_spam_patterns(text):
            return False, "❌ محتوای تبلیغاتی مجاز نیست", None
        
        # 4. بررسی حداقل طول معنادار
        if len(text.strip()) < 3:
            return False, "متن باید حداقل 3 کاراکتر باشد", None
        
        return True, "OK", None
    
    def validate_attachment_submission(
        self,
        name: str,
        description: str,
        max_name_length: int = 100,
        max_desc_length: int = 100
    ) -> Dict:
        """
        اعتبارسنجی کامل یک ارسال اتچمنت
        
        Returns:
            {
                'valid': bool,
                'name_valid': bool,
                'name_reason': str,
                'name_violation': dict or None,
                'desc_valid': bool,
                'desc_reason': str,
                'desc_violation': dict or None
            }
        """
        # بررسی نام
        name_valid, name_reason, name_violation = self.validate_text(
            name, 
            max_name_length,
            check_spam=True
        )
        
        # بررسی توضیحات (description اختیاری است)
        desc_valid = True
        desc_reason = "OK"
        desc_violation = None
        
        if description and description.strip():
            desc_valid, desc_reason, desc_violation = self.validate_text(
                description,
                max_desc_length,
                check_spam=True
            )
        
        return {
            'valid': name_valid and desc_valid,
            'name_valid': name_valid,
            'name_reason': name_reason,
            'name_violation': name_violation,
            'desc_valid': desc_valid,
            'desc_reason': desc_reason,
            'desc_violation': desc_violation
        }


# Singleton instance (optional)
_validator_instance = None


def get_validator(db):
    """دریافت instance از ContentValidator (singleton pattern)"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = ContentValidator(db)
    return _validator_instance
