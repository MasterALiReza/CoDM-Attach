"""
Base Handler Registry

کلاس پایه برای تمام registries
"""

from telegram.ext import Application


class BaseHandlerRegistry:
    """کلاس پایه برای ثبت handlers"""
    
    def __init__(self, application: Application, db):
        """
        Args:
            application: Telegram Application instance
            db: Database adapter instance
        """
        self.application = application
        self.db = db
    
    def register(self):
        """ثبت handlers - باید در کلاس‌های فرزند override شود"""
        raise NotImplementedError("Subclasses must implement register()")
