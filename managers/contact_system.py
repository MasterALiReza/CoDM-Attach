"""
سیستم حرفه‌ای تماس با ما (Contact Us) و مدیریت تیکت‌ها
این ماژول شامل:
- Ticket System با دسته‌بندی و اولویت
- FAQ System
- Feedback & Rating
- Direct Contact
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import json
from utils.logger import get_logger, log_db_operation, log_exception

logger = get_logger('contact', 'contact.log')


class TicketCategory(Enum):
    """دسته‌بندی تیکت‌ها"""
    BUG = "bug"  # گزارش باگ
    FEATURE_REQUEST = "feature_request"  # درخواست قابلیت جدید
    QUESTION = "question"  # سوال
    CONTENT_ISSUE = "content_issue"  # مشکل محتوا (اتچمنت اشتباه)
    CHANNEL_ISSUE = "channel_issue"  # مشکل کانال‌های اجباری
    OTHER = "other"  # سایر موارد


class TicketPriority(Enum):
    """اولویت تیکت"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(Enum):
    """وضعیت تیکت"""
    OPEN = "open"  # باز
    IN_PROGRESS = "in_progress"  # در حال بررسی
    WAITING_USER = "waiting_user"  # منتظر پاسخ کاربر
    RESOLVED = "resolved"  # حل شده
    CLOSED = "closed"  # بسته شده


class ContactSystem:
    """سیستم مدیریت تماس با ما و تیکت‌ها"""
    
    def __init__(self, db):
        """
        Args:
            db: DatabaseAdapter instance
        """
        self.db = db
        logger.info("ContactSystem initialized")
    
    # ==================== Ticket Management ====================
    
    @log_db_operation("create_ticket")
    def create_ticket(self, user_id: int, category: str, subject: str,
                     description: str, priority: str = "medium",
                     attachments: List[str] = None) -> Optional[int]:
        """
        ایجاد تیکت جدید
        
        Args:
            user_id: شناسه کاربر
            category: دسته‌بندی (bug, feature_request, question, etc.)
            subject: موضوع تیکت
            description: توضیحات کامل
            priority: اولویت (low, medium, high, critical)
            attachments: لیست file_id های تصاویر/فایل‌ها
            
        Returns:
            ticket_id یا None در صورت خطا
        """
        try:
            ticket_id = self.db.add_ticket(
                user_id=user_id,
                category=category,
                subject=subject,
                description=description,
                priority=priority,
                attachments=attachments or []
            )
            
            logger.info(f"Ticket created: ID={ticket_id}, User={user_id}, Category={category}")
            return ticket_id
            
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            log_exception(logger, e, "create_ticket")
            return None
    
    def get_ticket(self, ticket_id: int) -> Optional[Dict]:
        """دریافت اطلاعات یک تیکت"""
        try:
            return self.db.get_ticket(ticket_id)
        except Exception as e:
            logger.error(f"Error getting ticket {ticket_id}: {e}")
            return None
    
    def get_user_tickets(self, user_id: int, status: Optional[str] = None) -> List[Dict]:
        """
        دریافت تیکت‌های یک کاربر
        
        Args:
            user_id: شناسه کاربر
            status: فیلتر بر اساس وضعیت (اختیاری)
            
        Returns:
            لیست تیکت‌ها
        """
        try:
            return self.db.get_user_tickets(user_id, status)
        except Exception as e:
            logger.error(f"Error getting user tickets: {e}")
            return []
    
    def add_ticket_reply(self, ticket_id: int, user_id: int, 
                        message: str, is_admin: bool = False,
                        attachments: List[str] = None) -> bool:
        """
        افزودن پاسخ به تیکت
        
        Args:
            ticket_id: شناسه تیکت
            user_id: شناسه کاربر/ادمین
            message: متن پیام
            is_admin: آیا پاسخ از طرف ادمین است؟
            attachments: پیوست‌ها
            
        Returns:
            موفقیت/عدم موفقیت
        """
        try:
            success = self.db.add_ticket_reply(
                ticket_id=ticket_id,
                user_id=user_id,
                message=message,
                is_admin=is_admin,
                attachments=attachments or []
            )
            
            if success:
                # اگر ادمین پاسخ داد، وضعیت را به "waiting_user" تغییر بده
                if is_admin:
                    self.update_ticket_status(ticket_id, TicketStatus.WAITING_USER.value)
                # اگر کاربر پاسخ داد، وضعیت را به "in_progress" تغییر بده
                else:
                    self.update_ticket_status(ticket_id, TicketStatus.IN_PROGRESS.value)
                
                logger.info(f"Reply added to ticket {ticket_id} by {'admin' if is_admin else 'user'} {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error adding ticket reply: {e}")
            log_exception(logger, e, "add_ticket_reply")
            return False
    
    def get_ticket_replies(self, ticket_id: int) -> List[Dict]:
        """دریافت تمام پاسخ‌های یک تیکت"""
        try:
            return self.db.get_ticket_replies(ticket_id)
        except Exception as e:
            logger.error(f"Error getting ticket replies: {e}")
            return []
    
    def update_ticket_status(self, ticket_id: int, new_status: str) -> bool:
        """به‌روزرسانی وضعیت تیکت"""
        try:
            success = self.db.update_ticket_status(ticket_id, new_status)
            if success:
                logger.info(f"Ticket {ticket_id} status updated to {new_status}")
            return success
        except Exception as e:
            logger.error(f"Error updating ticket status: {e}")
            return False
    
    def update_ticket_priority(self, ticket_id: int, new_priority: str) -> bool:
        """به‌روزرسانی اولویت تیکت"""
        try:
            success = self.db.update_ticket_priority(ticket_id, new_priority)
            if success:
                logger.info(f"Ticket {ticket_id} priority updated to {new_priority}")
            return success
        except Exception as e:
            logger.error(f"Error updating ticket priority: {e}")
            return False
    
    def assign_ticket(self, ticket_id: int, admin_id: int) -> bool:
        """اختصاص تیکت به یک ادمین"""
        try:
            success = self.db.assign_ticket(ticket_id, admin_id)
            if success:
                logger.info(f"Ticket {ticket_id} assigned to admin {admin_id}")
            return success
        except Exception as e:
            logger.error(f"Error assigning ticket: {e}")
            return False
    
    def close_ticket(self, ticket_id: int, admin_id: int, resolution: str = "") -> bool:
        """بستن تیکت"""
        try:
            success = self.db.close_ticket(ticket_id, admin_id, resolution)
            if success:
                logger.info(f"Ticket {ticket_id} closed by admin {admin_id}")
            return success
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            return False
    
    # ==================== FAQ Management ====================
    
    def get_faqs(self, category: Optional[str] = None, lang: Optional[str] = None) -> List[Dict]:
        """
        دریافت سوالات متداول
        
        Args:
            category: فیلتر بر اساس دسته (اختیاری)
            
        Returns:
            لیست FAQ ها
        """
        try:
            return self.db.get_faqs(category, lang)
        except Exception as e:
            logger.error(f"Error getting FAQs: {e}")
            return []
    
    def search_faqs(self, query: str, lang: Optional[str] = None) -> List[Dict]:
        """جستجو در FAQ ها"""
        try:
            return self.db.search_faqs(query, lang)
        except Exception as e:
            logger.error(f"Error searching FAQs: {e}")
            return []
    
    def add_faq(self, question: str, answer: str, category: str = "general", lang: Optional[str] = None) -> bool:
        """افزودن FAQ جدید (فقط ادمین)"""
        try:
            if lang is None:
                lang = 'fa'
            success = self.db.add_faq(question, answer, category, lang)
            if success:
                logger.info(f"FAQ added: {question[:50]}... [{lang}]")
            return success
        except Exception as e:
            logger.error(f"Error adding FAQ: {e}")
            return False
    
    def increment_faq_views(self, faq_id: int) -> bool:
        """افزایش تعداد بازدید یک FAQ"""
        try:
            return self.db.increment_faq_views(faq_id)
        except Exception as e:
            logger.error(f"Error incrementing FAQ views: {e}")
            return False
    
    def mark_faq_helpful(self, faq_id: int, helpful: bool = True) -> bool:
        """ثبت رای مفید/نامفید برای FAQ"""
        try:
            return self.db.mark_faq_helpful(faq_id, helpful)
        except Exception as e:
            logger.error(f"Error marking FAQ helpful (id={faq_id}, helpful={helpful}): {e}")
            return False
    
    def vote_faq(self, user_id: int, faq_id: int, helpful: bool = True) -> dict:
        """ثبت/تغییر رأی کاربر برای FAQ (هر کاربر حداکثر ۱ رأی)"""
        try:
            return self.db.vote_faq(user_id, faq_id, helpful)
        except Exception as e:
            logger.error(f"Error voting faq (user={user_id}, faq={faq_id}, helpful={helpful}): {e}")
            return {"success": False, "action": "error"}
    
    # ==================== Feedback System ====================
    
    def submit_feedback(self, user_id: int, rating: int, 
                       category: str = "general",
                       message: str = "") -> bool:
        """
        ثبت بازخورد کاربر
        
        Args:
            user_id: شناسه کاربر
            rating: امتیاز (1-5)
            category: دسته بازخورد
            message: پیام اختیاری
            
        Returns:
            موفقیت/عدم موفقیت
        """
        try:
            if not 1 <= rating <= 5:
                logger.warning(f"Invalid rating: {rating}")
                return False
            
            success = self.db.add_feedback(user_id, rating, category, message)
            if success:
                logger.info(f"Feedback submitted by user {user_id}: {rating}⭐")
            return success
            
        except Exception as e:
            logger.error(f"Error submitting feedback: {e}")
            log_exception(logger, e, "submit_feedback")
            return False
    
    def get_feedback_stats(self) -> Dict:
        """دریافت آمار بازخوردها"""
        try:
            return self.db.get_feedback_stats()
        except Exception as e:
            logger.error(f"Error getting feedback stats: {e}")
            return {}
    
    # ==================== Statistics ====================
    
    def get_ticket_stats(self, admin_id: Optional[int] = None) -> Dict:
        """
        دریافت آمار تیکت‌ها
        
        Args:
            admin_id: فیلتر برای ادمین خاص (اختیاری)
            
        Returns:
            دیکشنری حاوی آمار
        """
        try:
            return self.db.get_ticket_stats(admin_id)
        except Exception as e:
            logger.error(f"Error getting ticket stats: {e}")
            return {}
    
    def get_pending_tickets_count(self) -> int:
        """تعداد تیکت‌های باز و در انتظار"""
        try:
            stats = self.get_ticket_stats()
            return stats.get('open', 0) + stats.get('in_progress', 0)
        except Exception as e:
            logger.error(f"Error getting pending tickets count: {e}")
            return 0
    
    # ==================== Utility ====================
    
    @staticmethod
    def format_category_name(category: str) -> str:
        """تبدیل نام دسته به فارسی"""
        category_map = {
            "bug": "🐛 گزارش باگ",
            "feature_request": "✨ درخواست قابلیت",
            "question": "❓ سوال",
            "content_issue": "📝 مشکل محتوا",
            "channel_issue": "📢 مشکل کانال",
            "other": "📌 سایر موارد"
        }
        return category_map.get(category, category)
    
    @staticmethod
    def format_priority_name(priority: str) -> str:
        """تبدیل اولویت به فارسی"""
        priority_map = {
            "low": "🟢 کم",
            "medium": "🟡 متوسط",
            "high": "🟠 بالا",
            "critical": "🔴 فوری"
        }
        return priority_map.get(priority, priority)
    
    @staticmethod
    def format_status_name(status: str) -> str:
        """تبدیل وضعیت به فارسی"""
        status_map = {
            "open": "🆕 باز",
            "in_progress": "⚙️ در حال بررسی",
            "waiting_user": "⏳ منتظر پاسخ شما",
            "resolved": "✅ حل شده",
            "closed": "🔒 بسته شده"
        }
        return status_map.get(status, status)
    
    def get_suggested_faqs(self, ticket_description: str, limit: int = 3, lang: Optional[str] = None) -> List[Dict]:
        """
        پیشنهاد FAQ های مرتبط قبل از ثبت تیکت
        
        Args:
            ticket_description: توضیحات تیکت
            limit: تعداد پیشنهادات
            
        Returns:
            لیست FAQ های مرتبط
        """
        try:
            # جستجو در FAQ ها
            results = self.search_faqs(ticket_description, lang)
            return results[:limit] if results else []
        except Exception as e:
            logger.error(f"Error getting suggested FAQs: {e}")
            return []
