"""
ماژول Support
Export کردن تمام handlers مربوط به پشتیبانی
"""

from .faq_handler import FAQHandler
from .ticket_handler import TicketHandler
from .direct_contact_handler import DirectContactHandler

__all__ = [
    'FAQHandler',
    'TicketHandler',
    'DirectContactHandler',
]
