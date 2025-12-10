"""Utilities to safely call Telegram edit methods.

Only suppresses the harmless "Message is not modified" BadRequest to avoid noisy errors
when the new content equals the current one. All other exceptions are propagated.
"""
from __future__ import annotations

from typing import Any
from telegram.error import BadRequest


async def safe_edit_message_text(query: Any, text: str, **kwargs: Any) -> None:
    """Safely call CallbackQuery.edit_message_text.

    Args:
        query: telegram.CallbackQuery (or object exposing edit_message_text coroutine)
        text: New text to set
        **kwargs: Passed through to edit_message_text

    Behavior:
        - Ignores BadRequest where the message is not modified
        - Re-raises all other exceptions
    """
    try:
        await query.edit_message_text(text, **kwargs)
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            # Silently ignore this benign case
            return
        raise
