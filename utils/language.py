from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.logger import get_logger
from config.config import DEFAULT_LANG, SUPPORTED_LANGS
from .i18n import t

logger = get_logger('language', 'app.log')



def get_user_lang(update: Update, context: ContextTypes.DEFAULT_TYPE, db) -> Optional[str]:
    if context and hasattr(context, 'user_data') and context.user_data.get("_lang"):
        return context.user_data.get("_lang")
    try:
        user_id = update.effective_user.id if update and update.effective_user else None
        if not user_id:
            return None
        lang = db.get_user_language(user_id)
        if lang in SUPPORTED_LANGS:
            context.user_data["_lang"] = lang
            return lang
    except Exception as e:
        logger.error(f"get_user_lang error: {e}")
    return None


async def ensure_language(update: Update, context: ContextTypes.DEFAULT_TYPE, db) -> bool:
    lang = get_user_lang(update, context, db)
    if lang:
        return True

    # bilingual prompt (no parse_mode to keep simple)
    message = t("lang.choose_bilingual", 'fa')
    keyboard = [
        [
            InlineKeyboardButton(t("lang.fa", 'fa'), callback_data="set_lang_fa"),
            InlineKeyboardButton(t("lang.en", 'fa'), callback_data="set_lang_en"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.message.reply_text(message, reply_markup=reply_markup)
    elif update.message:
        await update.message.reply_text(message, reply_markup=reply_markup)
    return False


def set_user_lang(update: Update, context: ContextTypes.DEFAULT_TYPE, db, lang: str) -> bool:
    user_id = update.effective_user.id if update and update.effective_user else None
    if not user_id:
        return False
    if lang not in SUPPORTED_LANGS:
        return False
    try:
        ok = db.set_user_language(user_id, lang)
        if ok:
            context.user_data["_lang"] = lang
        return ok
    except Exception as e:
        logger.error(f"set_user_lang error: {e}")
        return False
