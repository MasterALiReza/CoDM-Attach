"""
مدیریت سلاح‌ها
⚠️ این کد عیناً از user_handlers.py خط 418-596 کپی شده
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.config import WEAPON_CATEGORIES, CATEGORY_SETTINGS, GAME_MODES
from managers.channel_manager import require_channel_membership
from utils.logger import log_user_action, get_logger
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text
from handlers.user.base_user_handler import BaseUserHandler

logger = get_logger('user', 'user.log')


class WeaponHandler(BaseUserHandler):
    """مدیریت انتخاب و نمایش سلاح‌ها"""
    
    @require_channel_membership
    @log_user_action("show_weapons")

    async def show_weapons(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش سلاح‌های یک دسته با درنظرگرفتن فعال/غیرفعال بودن دسته"""
        query = update.callback_query
        await query.answer()
        
        category = query.data.replace("cat_", "")
        
        
        # بررسی فعال بودن دسته برای mode انتخاب شده
        from config.config import is_category_enabled
        mode = context.user_data.get('selected_mode', 'mp')
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not is_category_enabled(category, mode):
            mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}"
            await safe_edit_message_text(
                query,
                f"📍 {mode_name}\n\n{t('error.generic', lang)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"mode_{mode}")]])
            )
            return
        
        context.user_data['current_category'] = category
        weapons = self.db.get_weapons_in_category(category)
        if not weapons:
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="categories")]])
            await safe_edit_message_text(
                query,
                t("attachment.none", lang),
                reply_markup=reply_markup
            )
            return
        
        # ساخت keyboard با تعداد ستون‌های متغیر (AR و SMG: 3 ستونی، بقیه: 2 ستونی)
        from config import build_weapon_keyboard
        keyboard = build_weapon_keyboard(weapons, "wpn_", category, add_emoji=True)
        
        # اگر mode انتخاب شده، دکمه بازگشت به لیست دسته‌ها با mode
        # وگرنه بازگشت به انتخاب mode
        selected_mode = context.user_data.get('selected_mode')
        if selected_mode:
            # بازگشت به لیست سلاح‌ها با mode ذخیره شده
            mode_btn = t(f"mode.{selected_mode}_btn", lang)
            mode_short = t(f"mode.{selected_mode}_short", lang)
            back_text = f"{t('menu.buttons.back', lang)} ({t('mode.label', lang)}: {mode_btn})"
            keyboard.append([InlineKeyboardButton(back_text, callback_data=f"mode_{selected_mode}")])
            # نمایش mode در header
            category_name = t(f"category.{category}", lang)
            await safe_edit_message_text(
                query,
                f"📍 {t('mode.label', lang)}: {mode_short}\n**{category_name}**\n\n{t('weapon.choose', lang)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            # بازگشت به انتخاب mode (فلوی قدیمی)
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="categories")])
            category_name = t(f"category.{category}", lang)
            await safe_edit_message_text(
                query,
                f"**{category_name}**\n\n{t('weapon.choose', lang)}",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    
    @require_channel_membership
    @log_user_action("show_weapon_menu")

    async def show_weapon_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی انتخاب Mode برای سلاح یا مستقیم نمایش اتچمنت‌ها اگر mode از قبل انتخاب شده"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پشتیبانی از دو حالت کال‌بک:
        # 1) "wpn_{weapon}" (از لیست دسته)
        # 2) "wpn_{category}__{weapon}" (از نتایج جستجو)
        payload = query.data.replace("wpn_", "")
        if "__" in payload:
            category, weapon_name = payload.split("__", 1)
            context.user_data['current_category'] = category
            context.user_data['current_weapon'] = weapon_name
        else:
            weapon_name = payload
            category = context.user_data.get('current_category')
            context.user_data['current_weapon'] = weapon_name

        # اگر دسته تعیین نشده بود، آن را بر اساس دیتابیس پیدا کن
        if not category:
            for cat in WEAPON_CATEGORIES:
                try:
                    weapons = self.db.get_weapons_in_category(cat)
                except Exception:
                    weapons = []
                if weapon_name in weapons:
                    category = cat
                    context.user_data['current_category'] = category
                    break
        
        # اگر mode از قبل انتخاب شده (از فلوی جدید)، مستقیم نمایش بده
        selected_mode = context.user_data.get('selected_mode')
        if selected_mode:
            context.user_data['current_mode'] = selected_mode
            # نمایش مستقیم منوی اتچمنت‌ها
            weapon_data = self.db.get_weapon_attachments(category, weapon_name, mode=selected_mode)
            top_count = len(weapon_data.get('top_attachments', []))
            all_count = len(weapon_data.get('all_attachments', []))
            
            keyboard = []
            
            # دکمه برترها
            keyboard.append([InlineKeyboardButton(
                f"{t('weapon.menu.top', lang)} ({top_count})",
                callback_data="show_top"
            )])
            
            # دکمه همه اتچمنت‌ها
            keyboard.append([InlineKeyboardButton(
                f"{t('weapon.menu.all', lang)} ({all_count})",
                callback_data="show_all"
            )])
            
            # دکمه بازگشت به لیست سلاح‌ها
            keyboard.append([
                InlineKeyboardButton(t("menu.buttons.search", lang), callback_data="search_weapon"),
                InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"cat_{category}")
            ])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            mode_short = t(f"mode.{selected_mode}_btn", lang)
            mode_name = f"{t('mode.label', lang)}: {mode_short}"
            
            if all_count == 0:
                text = f"**🔫 {weapon_name}**\n**{mode_name}**\n\n{t('attachment.none', lang)}"
            else:
                text = f"**🔫 {weapon_name}**\n**{mode_name}**\n\n📊 {all_count}\n⭐ {top_count}"
            
            await safe_edit_message_text(
                query,
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
            # به‌روزرسانی کیبورد پایین
            try:
                last_key = context.user_data.get('kb_prompt_key')
                current_key = f"{weapon_name}_{selected_mode}"
                if last_key != current_key:
                    await query.message.reply_text(
                        t("success.generic", lang),
                        reply_markup=self._weapon_reply_keyboard(top_count, all_count, lang)
                    )
                    context.user_data['kb_prompt_key'] = current_key
            except Exception as e:
                logger.debug(f"خطا در ارسال guide prompt: {e}")
            
            return
        
        # دریافت تعداد اتچمنت‌ها برای هر mode (فلوی قدیمی - backward compatibility)
        br_data = self.db.get_weapon_attachments(category, weapon_name, mode="br")
        mp_data = self.db.get_weapon_attachments(category, weapon_name, mode="mp")
        
        br_count = len(br_data.get('all_attachments', []))
        mp_count = len(mp_data.get('all_attachments', []))
        
        # ساخت دکمه‌های انتخاب Mode
        keyboard = []
        
        keyboard.append([
            InlineKeyboardButton(
                f"{t('mode.br_short', lang)} ({br_count})",
                callback_data=f"mode_br_{weapon_name}"
            )
        ])
        
        keyboard.append([
            InlineKeyboardButton(
                f"{t('mode.mp_short', lang)} ({mp_count})",
                callback_data=f"mode_mp_{weapon_name}"
            )
        ])
        
        keyboard.append([
            InlineKeyboardButton(t("menu.buttons.search", lang), callback_data="search_weapon"),
            InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=f"cat_{category}")
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        text = f"**🔫 {weapon_name}**\n\n"
        text += t("mode.choose", lang)
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    @require_channel_membership
    @log_user_action("show_mode_menu")

    async def show_mode_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی اتچمنت‌های سلاح برای mode انتخاب شده"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پردازش callback: mode_{br|mp}_{weapon}
        data_parts = query.data.split("_", 2)
        if len(data_parts) < 3:
            return
        
        mode = data_parts[1]  # br یا mp
        weapon_name = data_parts[2]
        
        category = context.user_data.get('current_category')
        context.user_data['current_mode'] = mode
        
        weapon_data = self.db.get_weapon_attachments(category, weapon_name, mode=mode)
        top_count = len(weapon_data.get('top_attachments', []))
        all_count = len(weapon_data.get('all_attachments', []))
        
        keyboard = []
        
        # دکمه برترها
        keyboard.append([InlineKeyboardButton(
            f"{t('weapon.menu.top', lang)} ({top_count})",
            callback_data="show_top"
        )])
        
        # دکمه همه اتچمنت‌ها
        keyboard.append([InlineKeyboardButton(
            f"{t('weapon.menu.all', lang)} ({all_count})",
            callback_data="show_all"
        )])
        
        # دکمه بازگشت
        # اگر از فلوی جدید آمده (selected_mode)، به لیست سلاح‌ها برگرد
        # وگرنه به منوی انتخاب mode برگرد
        selected_mode = context.user_data.get('selected_mode')
        if selected_mode and selected_mode == mode:
            # برگشت به لیست سلاح‌ها
            back_callback = f"cat_{category}"
        else:
            # برگشت به منوی mode selection (فلوی قدیمی)
            back_callback = f"wpn_{weapon_name}"
        
        keyboard.append([
            InlineKeyboardButton(t("menu.buttons.search", lang), callback_data="search_weapon"),
            InlineKeyboardButton(t("menu.buttons.back", lang), callback_data=back_callback)
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        mode_short = t(f"mode.{mode}_short", lang)
        mode_name = f"{t('mode.label', lang)}: {mode_short}"
        
        if all_count == 0:
            text = f"**🔫 {weapon_name}**\n**{mode_name}**\n\n{t('attachment.none', lang)}"
        else:
            text = f"**🔫 {weapon_name}**\n**{mode_name}**\n\n📊 {all_count}\n⭐ {top_count}"
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # به‌روزرسانی کیبورد پایین
        try:
            last_key = context.user_data.get('kb_prompt_key')
            current_key = f"{weapon_name}_{mode}"
            if last_key != current_key:
                await query.message.reply_text(
                    t("weapon.keyboard_prompt", lang),
                    reply_markup=self._weapon_reply_keyboard(top_count, all_count, lang)
                )
                context.user_data['kb_prompt_key'] = current_key
        except Exception as e:
            logger.debug(f"خطا در ارسال guide prompt: {e}")
