import os
from telegram.ext import InlineQueryHandler, ChosenInlineResultHandler
from .base_registry import BaseHandlerRegistry
from handlers.inline.inline_handler import InlineHandler


class InlineHandlerRegistry(BaseHandlerRegistry):
    def __init__(self, application, db, bot_instance):
        super().__init__(application, db)
        self.bot = bot_instance

    def register(self):
        enabled = os.getenv('INLINE_MODE_ENABLED', 'false').lower() == 'true'
        if not enabled:
            return
        handler = InlineHandler(self.db)
        self.application.add_handler(InlineQueryHandler(handler.handle_inline_query), group=0)
        self.application.add_handler(ChosenInlineResultHandler(handler.handle_chosen_inline_result), group=0)
