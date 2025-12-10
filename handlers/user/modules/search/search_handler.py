"""
مدیریت جستجو
⚠️ این کد عیناً از user_handlers.py خط 1104-1294 کپی شده
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import time
from config.config import WEAPON_CATEGORIES
from managers.channel_manager import require_channel_membership
from utils.logger import log_user_action
from utils.language import get_user_lang
from utils.i18n import t
from handlers.user.base_user_handler import BaseUserHandler
from utils.telegram_safety import safe_edit_message_text

# Define SEARCHING state
SEARCHING = 3  # Must match the value in user_handlers.py: SELECTING_CATEGORY, SELECTING_WEAPON, VIEWING_ATTACHMENTS, SEARCHING = range(4)


class SearchHandler(BaseUserHandler):
    """مدیریت جستجو"""
    
    def __init__(self, db, main_menu_handler=None, category_handler=None, season_handler=None, suggested_handler=None, guides_handler=None, notification_handler=None, cms_user_handler=None):
        super().__init__(db)
        self.main_menu_handler = main_menu_handler
        self.category_handler = category_handler
        self.season_handler = season_handler
        self.suggested_handler = suggested_handler
        self.guides_handler = guides_handler
        self.notification_handler = notification_handler
        self.cms_user_handler = cms_user_handler

    async def search_start_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع جستجو از طریق پیام"""
        from datetime import datetime
        lang = get_user_lang(update, context, self.db) or 'fa'

        # اضافه کردن timestamp برای جلوگیری از duplicate detection
        now = datetime.now().strftime("%H:%M:%S")
        text = t('search.prompt', lang) + f" _{t('notification.updated', lang, time=now)}_"
        
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t('search.cancel', lang), callback_data="main_menu")
            ]]),
            parse_mode='Markdown'
        )
        return SEARCHING
    
    @log_user_action("search_start")
    async def search_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع جستجو"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        await safe_edit_message_text(
            query,
            t('search.prompt', lang),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t('search.cancel', lang), callback_data="main_menu")
            ]]),
            parse_mode='Markdown'
        )
        
        return SEARCHING
    
    @log_user_action("search_process")
    async def search_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش جستجو"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        query_text = update.message.text.strip()
        start_ts = time.time()
        results = self.db.search(query_text)
        elapsed_ms = int((time.time() - start_ts) * 1000)
        
        
        # بررسی فرمت خروجی برای backward compatibility
        if isinstance(results, dict):
            # Legacy format - for backward compatibility
            weapons_results = results.get('weapons', [])
            attachments_results = results.get('attachments', [])
        else:
            # PostgreSQL: List of tuples or List of dicts
            weapons_results = []
            attachments_results = results or []
            
            # استخراج سلاح‌های یکتا از نتایج اتچمنت‌ها
            unique_weapons = {}
            for item in attachments_results:
                category = item.get('category')
                weapon = item.get('weapon')
                if not category or not weapon:
                    continue
                weapon_key = f"{category}:{weapon}"
                if weapon_key not in unique_weapons:
                    unique_weapons[weapon_key] = {
                        'category': category,
                        'weapon': weapon
                    }
            weapons_results = list(unique_weapons.values())
        
        # ساخت هدر نتایج با شمارش صحیح
        try:
            total_results = len(attachments_results) + len(weapons_results)
        except Exception:
            total_results = len(attachments_results) if attachments_results else 0
        text = t('search.results', lang, query=query_text, count=total_results) + "\n\n"
        keyboard = []
        shown_all = set()  # جلوگیری از ساخت چندباره دکمه «همه اتچمنت‌ها» برای یک سلاح
        
        # ثبت آمار جستجو
        try:
            user_id = update.effective_user.id if update.effective_user else None
            if user_id:
                total_results = (len(attachments_results) + len(weapons_results)) if isinstance(results, dict) else len(attachments_results)
                self.db.track_search(user_id, query_text, int(total_results), float(elapsed_ms))
        except Exception:
            pass
        
        # نمایش سلاح‌های یافت‌شده + ساخت دکمه‌های پیش‌نمایش (برتر فصل / برتر / معمولی) و همه اتچمنت‌ها
        if weapons_results:
            text += f"**{t('search.weapons_header', lang)}**\n"
            for item in weapons_results[:5]:  # محدودسازی جهت زیبایی کیبورد
                category_key = item['category']
                category_name = t(f"category.{category_key}", lang)
                weapon_name = item['weapon']
                text += f"• {weapon_name} ({category_name})\n"
                
                # جمع‌آوری اتچمنت‌ها از هر دو mode
                mixed_attachments = []
                
                for mode in ['br', 'mp']:
                    all_atts = self.db.get_all_attachments(category_key, weapon_name, mode=mode)
                    top_atts = self.db.get_top_attachments(category_key, weapon_name, mode=mode)
                    season_atts = self.db.get_season_top_attachments_for_weapon(category_key, weapon_name, mode=mode)
                    
                    top_codes = {att['code'] for att in top_atts}
                    season_codes = {att['code'] for att in season_atts}
                    
                    for att in all_atts:
                        # تعیین اولویت: 1=season_top, 2=top, 3=normal
                        if att['code'] in season_codes:
                            priority = 1
                            badge = t('badge.season_top', lang)
                        elif att['code'] in top_codes:
                            priority = 2
                            badge = t('badge.top', lang)
                        else:
                            priority = 3
                            badge = ""
                        
                        mode_emoji = "🪂" if mode == 'br' else "🎮"
                        
                        mixed_attachments.append({
                            'att': att,
                            'mode': mode,
                            'priority': priority,
                            'badge': badge,
                            'mode_emoji': mode_emoji,
                            'category': category_key,
                            'weapon': weapon_name
                        })
                
                # مرتب‌سازی بر اساس اولویت (کم‌تر = بهتر)
                mixed_attachments.sort(key=lambda x: x['priority'])
                
                # نمایش 5 تای اول
                for item in mixed_attachments[:5]:
                    att = item['att']
                    mode_emoji = item['mode_emoji']
                    badge = item['badge']
                    mode = item['mode']
                    mode_text = t(f"mode.{mode}_short", lang)
                    
                    # ساخت متن دکمه
                    button_text = f"{mode_emoji} {mode_text} :  {att['name']}"
                    if badge:
                        button_text += f" {badge}"
                    
                    keyboard.append([InlineKeyboardButton(
                        button_text,
                        callback_data=f"qatt_{category_key}__{weapon_name}__{mode}__{att['code']}"
                    )])
                
                # دکمه «نمایش همه (Weapon)» 
                key = (category_key, weapon_name)
                if key not in shown_all:
                    keyboard.append([InlineKeyboardButton(
                        t('search.show_all_for_weapon', lang, weapon=weapon_name),
                        callback_data=f"all_{category_key}__{weapon_name}"
                    )])
                    shown_all.add(key)
            text += "\n"
        
        # نمایش اتچمنت‌های یافت‌شده + افزودن دکمه برای سلاح مربوطه (در صورت نبود قبلی)
        if attachments_results:
            text += f"**{t('search.attachments_header', lang)}**\n"
            
            # تبدیل نتایج به فرمت یکسان
            attachment_list = []
            if isinstance(results, dict):
                # Legacy format
                attachment_list = attachments_results[:10]
            else:
                # PostgreSQL format - support tuples or dicts
                for item in attachments_results[:10]:
                    attachment_list.append(item)
            
            for item in attachment_list:
                att = item['attachment']
                weapon_name = item['weapon']
                category_key = item['category']
                mode = item.get('mode', 'br')
                mode_short = t(f"mode.{mode}_btn", lang)
                mode_name = f"{t('mode.label', lang)}: {mode_short}"
                
                text += f"• {att['name']} ({t('attachment.code', lang)}: `{att['code']}`)\n"
                text += f"  {t('weapon.label', lang)}: {weapon_name} | {mode_name}\n"
                # برای اتچمنت‌های به‌دست‌آمده، یک دکمه "همه اتچمنت‌ها" هم اضافه شود (بدون تکرار)
                key = (category_key, weapon_name)
                if key not in shown_all:
                    keyboard.append([InlineKeyboardButton(
                        t('search.show_all_for_weapon', lang, weapon=weapon_name),
                        callback_data=f"all_{category_key}__{weapon_name}"
                    )])
                    shown_all.add(key)
            text += "\n"
        
        if not weapons_results and not attachments_results:
            text = t('search.no_results', lang, query=query_text)
        
        keyboard.append([InlineKeyboardButton(t('search.new', lang), callback_data="search")])
        keyboard.append([InlineKeyboardButton(t('menu.buttons.home', lang), callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        return ConversationHandler.END
    
    async def search_restart_silently(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """وقتی کاربر در حالت SEARCHING دوباره دکمه جستجو رو میزنه، بی‌صدا دوباره پیام رو نمایش بده - خط 1401"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        await update.message.reply_text(
            t('search.prompt', lang),
            reply_markup=InlineKeyboardMarkup([[ 
                InlineKeyboardButton(t('search.cancel', lang), callback_data="main_menu")
            ]]),
            parse_mode='Markdown'
        )
        # همچنان در حالت SEARCHING بمون
        return SEARCHING
    
    # ======= Search Cancellation Handlers =======
    async def search_cancel_and_show_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش دسته‌بندی‌ها"""
        if self.category_handler:
            await self.category_handler.show_categories_msg(update, context)
        return ConversationHandler.END
    
    async def search_cancel_and_season_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش برترهای فصل"""
        if self.season_handler:
            await self.season_handler.season_top_select_mode_msg(update, context)
        return ConversationHandler.END
    
    async def search_cancel_and_season_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش لیست برترها"""
        if self.season_handler:
            await self.season_handler.season_top_list_select_mode_msg(update, context)
        return ConversationHandler.END
    
    async def search_cancel_and_suggested(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش اتچمنت‌های پیشنهادی"""
        if self.suggested_handler:
            await self.suggested_handler.suggested_attachments_select_mode_msg(update, context)
        return ConversationHandler.END
    
    async def search_cancel_and_game_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش تنظیمات بازی"""
        if self.guides_handler:
            await self.guides_handler.game_settings_menu(update, context)
        return ConversationHandler.END
    
    async def search_cancel_and_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش راهنما"""
        # HelpHandler در UserHandlerRegistry ساخته می‌شود و به صورت داینامیک به
        # SearchHandler تزریق می‌شود (self.help_handler). اگر موجود باشد،
        # همان متد help_command_msg را صدا می‌زنیم تا تجربهٔ کاربر یکسان بماند.
        if hasattr(self, "help_handler") and self.help_handler is not None:
            await self.help_handler.help_command_msg(update, context)
        return ConversationHandler.END
    
    async def search_cancel_and_notifications(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش تنظیمات اعلان"""
        if self.notification_handler:
            context.user_data['_notification_shown'] = True
            await self.notification_handler.notification_settings(update, context)
        return ConversationHandler.END

    async def search_cancel_and_show_mode_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش انتخاب مود"""
        if self.category_handler:
            await self.category_handler.show_mode_selection_msg(update, context)
        return ConversationHandler.END
    
    async def search_cancel_and_cms(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """لغو بی‌صدا جستجو و نمایش CMS"""
        if self.cms_user_handler:
            await self.cms_user_handler.cms_home_msg(update, context)
        return ConversationHandler.END

    async def send_attachment_quick(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ارسال سریع اتچمنت از نتایج جستجو"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from utils.logger import get_logger, log_exception
        logger = get_logger('user', 'user.log')
        
        query = update.callback_query
        await query.answer()
        
        # Parse callback data: qatt_{category}__{weapon}__{mode}__{code}
        try:
            payload = query.data.replace("qatt_", "")
            parts = payload.split("__")
            
            if len(parts) != 4:
                logger.error(f"Invalid quick attachment callback: {query.data}")
                return
            
            category, weapon, mode, code = parts
        except Exception as e:
            logger.error(f"Error parsing quick attachment callback: {e}")
            return
        
        # دریافت اتچمنت
        attachments = self.db.get_all_attachments(category, weapon, mode=mode)
        selected = next((att for att in attachments if att.get('code') == code), None)
        
        if not selected:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t('attachment.not_found', lang), show_alert=True)
            return
        
        # ارسال
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_short = t(f"mode.{mode}_btn", lang)
        cat_name = t(f"category.{category}", lang)
        caption = f"**{selected['name']}**\n"
        caption += f"{t('weapon.label', lang)}: {weapon} ({cat_name})\n"
        caption += f"{t('mode.label', lang)}: {mode_short}\n"
        caption += f"{t('attachment.code', lang)}: `{selected['code']}`\n\n{t('attachment.tap_to_copy', lang)}"
        
        # آمار بازخورد + ثبت بازدید
        att_id = selected.get('id')
        stats = self.db.get_attachment_stats(att_id, period='all') if att_id else {}
        like_count = stats.get('like_count', 0)
        dislike_count = stats.get('dislike_count', 0)
        
        if att_id:
            self.db.track_attachment_view(query.from_user.id, att_id)
            
        feedback_kb = None
        if att_id:
            feedback_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                    InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
                ],
                [InlineKeyboardButton(t('attachment.copy_code', lang), callback_data=f"att_copy_{att_id}")],
                [InlineKeyboardButton(t('attachment.feedback', lang), callback_data=f"att_fb_{att_id}")]
            ])
        
        try:
            if selected.get('image'):
                await query.message.reply_photo(
                    photo=selected['image'], 
                    caption=caption, 
                    parse_mode='Markdown',
                    reply_markup=feedback_kb
                )
            else:
                await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=feedback_kb)
        except Exception as e:
            logger.error(f"Error sending quick attachment: {e}")
            log_exception(logger, e, "context")
            await query.message.reply_text(caption, parse_mode='Markdown')

    async def attachment_detail_with_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش جزئیات اتچمنت با مود مشخص (از جستجو)"""
        # attm_{category}__{weapon}__{code}__{mode}
        # This seems to be the same logic as view_attachment_from_notification but with different prefix
        # Reuse logic or implement similar
        return await self.send_attachment_quick(update, context) # Logic is very similar, maybe just redirect?
        # Wait, send_attachment_quick expects "qatt_" prefix and specific order.
        # attachment_detail_with_mode expects "attm_" prefix.
        # Let's implement it properly.
        
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from utils.logger import get_logger, log_exception
        logger = get_logger('user', 'user.log')
        
        query = update.callback_query
        await query.answer()
        
        try:
            payload = query.data.replace("attm_", "")
            # Check if it has double underscore separator
            parts = payload.split("__")
            if len(parts) != 4:
                 # Maybe it's the other format?
                 # UserHandlers had: category, weapon, code, mode = parts
                 pass
            
            category, weapon, code, mode = parts
        except Exception:
             # Try parsing differently if needed, but for now assume standard format
             return

        # Reuse send_attachment_quick logic by mocking payload? No, just copy paste or extract common method.
        # I'll just copy logic for now to be safe.
        
        attachments = self.db.get_all_attachments(category, weapon, mode=mode)
        selected = next((att for att in attachments if att.get('code') == code), None)
        
        if not selected:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.answer(t('attachment.not_found', lang), show_alert=True)
            return
            
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_short = t(f"mode.{mode}_btn", lang)
        cat_name = t(f"category.{category}", lang)
        caption = f"**{selected['name']}**\n"
        caption += f"{t('weapon.label', lang)}: {weapon} ({cat_name})\n"
        caption += f"{t('mode.label', lang)}: {mode_short}\n"
        caption += f"{t('attachment.code', lang)}: `{selected['code']}`\n\n{t('attachment.tap_to_copy', lang)}"
        
        att_id = selected.get('id')
        stats = self.db.get_attachment_stats(att_id, period='all') if att_id else {}
        like_count = stats.get('like_count', 0)
        dislike_count = stats.get('dislike_count', 0)
        
        if att_id:
            self.db.track_attachment_view(query.from_user.id, att_id)
            
        feedback_kb = None
        if att_id:
            feedback_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                    InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
                ],
                [InlineKeyboardButton(t('attachment.copy_code', lang), callback_data=f"att_copy_{att_id}")],
                [InlineKeyboardButton(t('attachment.feedback', lang), callback_data=f"att_fb_{att_id}")]
            ])
            
        try:
            if selected.get('image'):
                await query.message.reply_photo(
                    photo=selected['image'], 
                    caption=caption, 
                    parse_mode='Markdown',
                    reply_markup=feedback_kb
                )
            else:
                await query.message.reply_text(caption, parse_mode='Markdown', reply_markup=feedback_kb)
        except Exception:
            pass
