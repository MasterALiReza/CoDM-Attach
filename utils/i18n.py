import json
from pathlib import Path
from typing import Dict
from utils.logger import get_logger

logger = get_logger('i18n', 'app.log')

_translations: Dict[str, Dict] = {}
_locales_dir = Path(__file__).resolve().parent.parent / "locales"


def _load_translations(lang: str) -> Dict:
    if lang in _translations:
        return _translations[lang]
    locale_file = _locales_dir / f"{lang}.json"
    if not locale_file.exists():
        logger.warning(f"Locale file not found: {locale_file}")
        return {}
    try:
        with open(locale_file, 'r', encoding='utf-8') as f:
            _translations[lang] = json.load(f)
            return _translations[lang]
    except Exception as e:
        logger.error(f"Failed to load translations for '{lang}': {e}")
        return {}


def t(key: str, lang: str = 'fa', **kwargs) -> str:
    """Return localized text for the given key and language.

    Fallback order:
    1. locales/{lang}.json
    2. locales/{FALLBACK_LANG}.json
    3. config.config.MESSAGES (legacy Persian messages)
    4. The key itself
    """

    text = None
    try:
        # 1) Try current language
        translations = _load_translations(lang)
        text = translations.get(key)

        # 2) Fallback to global fallback language
        if text is None:
            try:
                from config.config import FALLBACK_LANG, MESSAGES

                if lang != FALLBACK_LANG:
                    fallback_translations = _load_translations(FALLBACK_LANG)
                    text = fallback_translations.get(key)

                # 3) Legacy fallback to MESSAGES dict
                if text is None:
                    text = MESSAGES.get(key, key)
            except Exception:
                # If config import fails for any reason, fall back to the key
                text = key
    except Exception:
        text = key

    if text is None:
        text = key

    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception as e:
            logger.error(f"Format error for key '{key}': {e}")
    return text


def kb(key: str, lang: str = 'fa') -> str:
    return t(key, lang)


def reload_translations():
    _translations.clear()
    logger.info("Translation cache cleared")
