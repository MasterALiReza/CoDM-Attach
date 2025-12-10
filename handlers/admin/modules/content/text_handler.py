"""
ماژول مدیریت متون ربات (Bot Texts)
مسئول: ویرایش پیام‌های خوش‌آمد و راهنما
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from handlers.admin.modules.base_handler import BaseAdminHandler
from core.security.role_manager import require_permission, Permission
from handlers.admin.admin_states import ADMIN_MENU, TEXT_EDIT
from utils.logger import get_logger
from utils.i18n import t, reload_translations
from utils.language import get_user_lang
from pathlib import Path
import json
import os
import re

logger = get_logger('text', 'admin.log')


class TextHandler(BaseAdminHandler):
    """
    مدیریت متون ربات
    
    Features:
    - ویرایش متن خوش‌آمد
    - ویرایش متن راهنما
    - ذخیره در config.py
    - پیش‌نمایش متن فعلی
    """
    
    def __init__(self, db):
        """مقداردهی اولیه"""
        super().__init__(db)
        logger.info("TextHandler initialized")
    
    # ==================== Main Menu ====================
    
    @require_permission(Permission.MANAGE_TEXTS)
    async def texts_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        منوی ویرایش پیام‌های عمومی ربات (دو‌زبانه)
        
        Options:
        - متن خوش‌آمد (welcome)
        - متن راهنما (help.text)
        """
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'

        text = (
            t("admin.texts.menu.title", lang) + "\n\n" +
            t("admin.texts.menu.desc", lang)
        )

        keyboard = [
            [InlineKeyboardButton(t("admin.texts.buttons.edit_welcome", lang), callback_data="text_edit_welcome")],
            [InlineKeyboardButton(t("admin.texts.buttons.edit_help", lang), callback_data="text_edit_help")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")]
        ]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        logger.info("Texts menu shown")
        return ADMIN_MENU
    
    # ==================== Edit Start ====================
    
    @require_permission(Permission.MANAGE_TEXTS)
    async def text_edit_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        شروع ویرایش یکی از پیام‌ها (با انتخاب زبان)
        
        Callback data:
        - text_edit_welcome: انتخاب زبان برای ویرایش خوش‌آمد
        - text_edit_help: انتخاب زبان برای ویرایش راهنما
        - text_edit_welcome_lang_fa|en: ورود به مرحله ویرایش خوش‌آمد برای زبان انتخاب‌شده
        - text_edit_help_lang_fa|en: ورود به مرحله ویرایش راهنما برای زبان انتخاب‌شده
        
        Steps:
        1. انتخاب زبان
        2. نمایش متن فعلی از locales/{lang}.json
        3. درخواست متن جدید
        """
        query = update.callback_query
        await query.answer()

        lang_ui = get_user_lang(update, context, self.db) or 'fa'
        data = query.data

        # مرحله 1: انتخاب زبان برای کلید انتخابی
        if data in ('text_edit_welcome', 'text_edit_help'):
            key = 'welcome' if data == 'text_edit_welcome' else 'help.text'
            context.user_data['text_key'] = key
            # پاک کردن زبان قبلی در صورت وجود
            context.user_data.pop('text_lang', None)

            title_label = t('admin.texts.item.welcome', lang_ui) if key == 'welcome' else t('admin.texts.item.help', lang_ui)
            text = t('admin.texts.choose_language', lang_ui)
            keyboard = [
                [InlineKeyboardButton(t('lang.fa', lang_ui), callback_data=f"{data}_lang_fa")],
                [InlineKeyboardButton(t('lang.en', lang_ui), callback_data=f"{data}_lang_en")],
                [InlineKeyboardButton(t('menu.buttons.back', lang_ui), callback_data="admin_menu_return")]
            ]
            await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
            logger.info(f"Language selection for key: {key}")
            return ADMIN_MENU

        # مرحله 2: ورود به حالت ویرایش برای زبان انتخابی
        key = 'welcome' if data.startswith('text_edit_welcome_lang_') else ('help.text' if data.startswith('text_edit_help_lang_') else None)
        if key is None:
            logger.warning(f"Unknown text edit action: {data}")
            return ADMIN_MENU

        edit_lang = 'fa' if data.endswith('_fa') else 'en'
        context.user_data['text_key'] = key
        context.user_data['text_lang'] = edit_lang

        # دریافت متن فعلی از i18n (fallback خودکار دارد)
        cur = t(key, edit_lang)
        preview = (cur or '').strip()
        if len(preview) > 500:
            preview = preview[:500] + '…'

        title_label = t('admin.texts.item.welcome', lang_ui) if key == 'welcome' else t('admin.texts.item.help', lang_ui)
        lang_name = t('lang.fa', lang_ui) if edit_lang == 'fa' else t('lang.en', lang_ui)
        msg = (
            t('admin.texts.edit.title', lang_ui, title=title_label, lang_name=lang_name) + "\n\n" +
            t('admin.texts.edit.prompt', lang_ui) + "\n\n" +
            t('admin.texts.edit.current_header', lang_ui) + "\n" +
            f"{preview}"
        )

        kb = [[InlineKeyboardButton(t('menu.buttons.cancel', lang_ui), callback_data="admin_cancel")]]
        await query.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))

        logger.info(f"Started editing text: {key} ({edit_lang})")
        return TEXT_EDIT
    
    # ==================== Edit Received ====================
    
    @require_permission(Permission.MANAGE_TEXTS)
    async def text_edit_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        دریافت متن جدید و ذخیره
        
        Validation:
        - باید متن باشد (نه عکس/ویدیو)
        - کلید معتبر (welcome/help.text) و زبان معتبر (fa/en)
        
        Actions:
        1. اعتبارسنجی
        2. ذخیره در فایل locales/{lang}.json
        3. پاک کردن کش ترجمه‌ها
        4. نمایش پیام تایید
        """
        if not update.message or not update.message.text:
            lang_ui = get_user_lang(update, context, self.db) or 'fa'
            await update.message.reply_text(t('admin.texts.error.text_only', lang_ui))
            return TEXT_EDIT

        key = context.user_data.get('text_key')
        edit_lang = context.user_data.get('text_lang')
        if key not in ('welcome', 'help.text') or edit_lang not in ('fa', 'en'):
            lang_ui = get_user_lang(update, context, self.db) or 'fa'
            await update.message.reply_text(t('admin.texts.error.invalid_key', lang_ui))
            logger.error(f"Invalid text key/lang: key={key} lang={edit_lang}")
            return ADMIN_MENU

        new_text = update.message.text

        # ذخیره در فایل locale
        ok = self._persist_locale_text(edit_lang, key, new_text)
        # پاک کردن کش ترجمه‌ها تا تغییرات فوراً اعمال شوند
        try:
            reload_translations()
        except Exception:
            pass

        lang_ui = get_user_lang(update, context, self.db) or 'fa'
        if ok:
            await update.message.reply_text(t('admin.texts.saved', lang_ui))
            logger.info(f"Text {key} ({edit_lang}) updated successfully")
        else:
            await update.message.reply_text(t('admin.texts.saved_memory_only', lang_ui))
            logger.warning(f"Failed to persist text {key} ({edit_lang}) to locale file")

        # پاکسازی داده‌های موقت
        context.user_data.pop('text_key', None)
        context.user_data.pop('text_lang', None)

        return ADMIN_MENU
    
    # ==================== Helper Methods ====================
    
    def _persist_locale_text(self, lang: str, key: str, new_value: str) -> bool:
        """
        ذخیره متن جدید در فایل locales/{lang}.json
        
        Args:
            lang: 'fa' یا 'en'
            key: کلید پیام ('welcome' یا 'help.text')
            new_value: متن جدید
        """
        try:
            # نرمال‌سازی پایان خطوط
            new_value_norm = (new_value or "").replace('\r\n', '\n')

            # مسیر فایل locale
            project_root = Path(__file__).resolve().parents[4]
            locale_path = project_root / 'locales' / f'{lang}.json'
            if not locale_path.exists():
                logger.error(f"Locale file not found: {locale_path}")
                return False

            with open(locale_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            data[key] = new_value_norm

            with open(locale_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.info(f"Persisted locale text: {key} ({lang}) -> {locale_path}")
            return True
        except Exception as e:
            logger.error(f"Error persisting locale text: {e}")
            return False

    def _persist_message_text(self, key: str, new_value: str) -> bool:
        """
        ذخیره متن جدید در فایل config.py
        
        Args:
            key: کلید پیام (welcome/help_text)
            new_value: متن جدید
        
        Returns:
            True اگر ذخیره موفق باشد
        
        Steps:
        1. خواندن config.py
        2. جایگزینی متن
        3. نوشتن مجدد
        4. به‌روزرسانی MESSAGES در حافظه
        """
        from config import config as config_module
        import os
        
        # نرمال‌سازی پایان خطوط
        new_value_norm = (new_value or "").replace('\r\n', '\n')
        
        try:
            config_path = os.path.join(os.path.dirname(config_module.__file__), 'config.py')
            
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # ساخت الگوهای قابل انطباق با هر دو حالت تک‌خطی و چندخطی (triple-quoted)
            # کلید می‌تواند با ' یا " تعریف شده باشد
            key_prefix = rf'(["\']{re.escape(key)}["\']\s*:\s*)'
            pattern_triple_dq = key_prefix + r'("""[\s\S]*?""")'
            pattern_triple_sq = key_prefix + r"('''[\s\S]*?''')"
            pattern_double = key_prefix + r'"((?:\\.|[^"\\])*)"'
            pattern_single = key_prefix + r"'((?:\\.|[^'\\])*)'"
            
            # آماده‌سازی مقدار جدید برای سبک‌های مختلف نقل‌قول
            # برای triple-quoted لازم است توالی سه‌تایی نقل‌قول escape شود
            tqd_val = new_value_norm.replace('"""', r'\"\"\"')
            tqs_val = new_value_norm.replace("'''", r"\'\'\'")
            
            replaced = False
            
            def try_sub(pat: str, repl: str) -> int:
                nonlocal content, replaced
                new_content, count = re.subn(pat, repl, content, count=1, flags=re.DOTALL)
                if count:
                    content = new_content
                    replaced = True
                return count
            
            # ابتدا تلاش برای جایگزینی در حالت‌های چندخطی
            if not try_sub(pattern_triple_dq, rf'\1"""{tqd_val}"""'):
                if not try_sub(pattern_triple_sq, rf"\1'''{tqs_val}'''"):
                    # اگر مقدار جدید چندخطی است، سبک را به triple-quoted ارتقاء بده
                    if '\n' in new_value_norm:
                        if not try_sub(pattern_double, rf'\1"""{tqd_val}"""'):
                            try_sub(pattern_single, rf"\1'''{tqs_val}'''")
                    else:
                        # حالت تک‌خطی - با نقل‌قول موجود جایگزین کن
                        escaped_dq = new_value_norm.replace('\\', '\\\\').replace('"', '\\"')
                        escaped_sq = new_value_norm.replace('\\', '\\\\').replace("'", "\\'")
                        if not try_sub(pattern_double, rf'\1"{escaped_dq}"'):
                            try_sub(pattern_single, rf"\1'{escaped_sq}'")
            
            if not replaced:
                logger.error(f"Could not find key {key} in config.py")
                # به‌روزرسانی در حافظه به عنوان fallback
                try:
                    from config.config import MESSAGES
                    MESSAGES[key] = new_value_norm
                except Exception:
                    pass
                return False
            
            # نوشتن محتوای جدید در فایل
            with open(config_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # به‌روزرسانی در حافظه
            from config.config import MESSAGES
            MESSAGES[key] = new_value_norm
            
            logger.info(f"Successfully persisted text for key: {key}")
            return True
            
        except FileNotFoundError:
            logger.error("Config file not found while persisting message text")
        except Exception as e:
            logger.error(f"Error persisting message text: {e}")
        
        # در صورت هرگونه خطا، حداقل در حافظه به‌روزرسانی می‌کنیم
        try:
            from config.config import MESSAGES
            MESSAGES[key] = new_value_norm
        except Exception:
            pass
        return False
