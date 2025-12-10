"""
مدیریت اتچمنت‌های پیشنهادی
⚠️ این کد عیناً از user_handlers.py خط 1874-2309 کپی شده
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.config import WEAPON_CATEGORIES, ITEMS_PER_PAGE
from managers.channel_manager import require_channel_membership
from utils.logger import log_user_action
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text
from handlers.user.base_user_handler import BaseUserHandler
from typing import Tuple
import math


class SuggestedHandler(BaseUserHandler):
    """مدیریت اتچمنت‌های پیشنهادی"""
    
    @require_channel_membership
    @log_user_action("suggested_attachments_select_mode")
    async def suggested_attachments_select_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب mode برای اتچمنت‌های پیشنهادی"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # بررسی تعداد اتچمنت‌های پیشنهادی
        br_count = self.db.get_suggested_count('br')
        mp_count = self.db.get_suggested_count('mp')
        
        keyboard = []
        # دکمه‌ها به صورت دو ستونه - BR راست، MP چپ
        mode_row = []
        if br_count > 0:
            mode_row.append(InlineKeyboardButton(f"{t('mode.br_btn', lang)} ({br_count})", callback_data="suggested_mode_br"))
        if mp_count > 0:
            mode_row.append(InlineKeyboardButton(f"{t('mode.mp_btn', lang)} ({mp_count})", callback_data="suggested_mode_mp"))
        if mode_row:
            keyboard.append(mode_row)
        
        if not keyboard:
            await safe_edit_message_text(
                query,
                t("attachment.none", lang),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")]
                ])
            )
            return
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="main_menu")])
        
        text = t("menu.buttons.suggested", lang) + "\n\n" + t("suggested.choose_mode", lang)
        
        try:
            await safe_edit_message_text(
                query,
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            # اگر پیام قبلی متن نداشت (مثلاً عکس بود)، پیام جدید بفرست
            await query.message.delete()
            await query.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    @require_channel_membership
    @log_user_action("suggested_attachments_select_mode_msg")
    async def suggested_attachments_select_mode_msg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب mode برای اتچمنت‌های پیشنهادی (از طریق پیام)"""
        from datetime import datetime
        lang = get_user_lang(update, context, self.db) or 'fa'
        # بررسی تعداد اتچمنت‌های پیشنهادی
        br_count = self.db.get_suggested_count('br')
        mp_count = self.db.get_suggested_count('mp')
        
        keyboard = []
        # دکمه‌ها به صورت دو ستونه - BR راست، MP چپ
        mode_row = []
        if br_count > 0:
            mode_row.append(InlineKeyboardButton(f"{t('mode.br_btn', lang)} ({br_count})", callback_data="suggested_mode_br"))
        if mp_count > 0:
            mode_row.append(InlineKeyboardButton(f"{t('mode.mp_btn', lang)} ({mp_count})", callback_data="suggested_mode_mp"))
        if mode_row:
            keyboard.append(mode_row)
        
        if not keyboard:
            await update.message.reply_text(
                t('attachment.none', lang),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t('menu.buttons.home', lang), callback_data="main_menu")]
                ])
            )
            return
        
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="main_menu")])
        
        # اضافه کردن timestamp برای جلوگیری از duplicate detection
        now = datetime.now().strftime("%H:%M:%S")
        text = t('menu.buttons.suggested', lang) + f" _{t('notification.updated', lang, time=now)}_\n\n" + t('suggested.choose_mode', lang)
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    
    @require_channel_membership
    @log_user_action("suggested_media_with_mode")
    async def suggested_media_with_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیست سلاح‌هایی که اتچمنت پیشنهادی دارند"""
        query = update.callback_query
        await query.answer()
        
        # استخراج mode از callback_data: suggested_mode_{mode}
        mode = query.data.replace("suggested_mode_", "")
        context.user_data['suggested_mode'] = mode
        
        # دریافت اتچمنت‌های پیشنهادی
        lang = get_user_lang(update, context, self.db) or 'fa'
        items = self.db.get_suggested_ranked(mode)
        mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_btn', lang)}"
        
        if not items:
            await safe_edit_message_text(
                query,
                t('attachment.none', lang),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="suggested_attachments")],
                    [InlineKeyboardButton(t('menu.buttons.home', lang), callback_data="main_menu")]
                ])
            )
            return
        
        # گروه‌بندی اتچمنت‌ها بر اساس سلاح
        weapons_dict = {}
        for item in items:
            category = (item or {}).get('category')
            weapon = (item or {}).get('weapon')
            attachment = (item or {}).get('attachment', {})
            key = f"{category}__{weapon}"
            if key not in weapons_dict:
                weapons_dict[key] = {
                    'category': category,
                    'weapon': weapon,
                    'count': 0,
                    'total_likes': 0
                }
            weapons_dict[key]['count'] += 1
            weapons_dict[key]['total_likes'] += attachment.get('likes', 0)
        
        # ساخت کیبورد دو ستونه
        keyboard = []
        weapons_list = sorted(weapons_dict.items(), key=lambda x: x[1]['weapon'])
        
        for i in range(0, len(weapons_list), 2):
            row = []
            key1, data1 = weapons_list[i]
            cat_emoji = WEAPON_CATEGORIES.get(data1['category'], '🔫').split()[0]
            likes1 = data1['total_likes']
            button_text1 = f"{cat_emoji} {data1['weapon']} ({data1['count']})"
            if likes1 > 0:
                button_text1 += f" 👍{likes1}"
            row.append(InlineKeyboardButton(
                button_text1,
                callback_data=f"sugg_wpn_{mode}_{key1}"
            ))
            
            if i + 1 < len(weapons_list):
                key2, data2 = weapons_list[i + 1]
                cat_emoji2 = WEAPON_CATEGORIES.get(data2['category'], '🔫').split()[0]
                likes2 = data2['total_likes']
                button_text2 = f"{cat_emoji2} {data2['weapon']} ({data2['count']})"
                if likes2 > 0:
                    button_text2 += f" 👍{likes2}"
                row.append(InlineKeyboardButton(
                    button_text2,
                    callback_data=f"sugg_wpn_{mode}_{key2}"
                ))
            
            keyboard.append(row)
        
        # افزودن دکمه نمایش لیست متنی
        keyboard.append([InlineKeyboardButton(t('list.show', lang), callback_data=f"suggested_list_mode_{mode}")])
        # دکمه بازگشت
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="suggested_attachments")])
        
        text = t('suggested.weapons_title', lang, mode=mode_name) + "\n\n" + t('suggested.select_weapon', lang)
        
        try:
            await safe_edit_message_text(
                query,
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception:
            # اگر پیام قبلی متن نداشت (مثلاً عکس بود)، پیام جدید بفرست
            await query.message.delete()
            await query.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    @require_channel_membership
    @log_user_action("suggested_weapon_attachments")
    async def suggested_weapon_attachments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیست اتچمنت‌های پیشنهادی یک سلاح"""
        query = update.callback_query
        await query.answer()
        
        # استخراج mode و weapon از callback_data: sugg_wpn_{mode}_{category}__{weapon}
        parts = query.data.replace("sugg_wpn_", "").split("_", 1)
        mode = parts[0]
        weapon_key = parts[1]  # category__weapon
        category, weapon = weapon_key.split("__")
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_btn', lang)}"
        cat_name = t(f"category.{category}", lang)
        
        # دریافت اتچمنت‌های پیشنهادی با فیلتر
        weapon_attachments = self.db.get_suggested_ranked(mode, category=category, weapon=weapon)
        
        if not weapon_attachments:
            await safe_edit_message_text(
                query,
                t('attachment.none', lang),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"suggested_mode_{mode}")]
                ])
            )
            return
        
        # ساخت کیبورد لیست اتچمنت‌ها
        keyboard = []
        for item in weapon_attachments:
            att = (item or {}).get('attachment', {})
            priority_emoji = self._get_priority_emoji_for_suggested(att.get('priority', 500))
            att_id = att['id']
            likes = att.get('likes', 0)
            
            button_text = f"{priority_emoji} {att['name']}"
            if likes > 0:
                button_text += f" 👍{likes}"
            
            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"sugg_send_{mode}_{att_id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"suggested_mode_{mode}")])
        
        from config.config import WEAPON_CATEGORIES
        cat_name_en = t(f"category.{category}", lang)
        
        text = (
            t('suggested.attachments_title', lang) + "\n\n"
            f"{t('weapon.label', lang)}: **{weapon}**\n"
            f"{t('category.label', lang)}: {cat_name_en}\n"
            f"{mode_name}\n\n"
            + t('suggested.select_attachment', lang)
        )
        
        # اگر پیام فعلی عکس است، پیام جدید بفرست
        if query.message.photo:
            await query.message.reply_text(
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            # اگر پیام متنی است، edit کن
            await safe_edit_message_text(
                query,
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    
    @require_channel_membership
    @log_user_action("suggested_send_attachment")
    async def suggested_send_attachment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ارسال یک اتچمنت پیشنهادی"""
        query = update.callback_query
        await query.answer()
        
        # استخراج mode و attachment_id از callback_data: sugg_send_{mode}_{att_id}
        parts = query.data.replace("sugg_send_", "").split("_", 1)
        mode = parts[0]
        att_id = int(parts[1])
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_btn', lang)}"
        
        # دریافت تمام اتچمنت‌های پیشنهادی
        items = self.db.get_suggested_ranked(mode)
        
        # پیدا کردن اتچمنت مورد نظر
        target_attachment = None
        target_category = None
        target_weapon = None
        
        for item in items:
            att = (item or {}).get('attachment', {})
            if att.get('id') == att_id:
                target_attachment = att
                target_category = (item or {}).get('category')
                target_weapon = (item or {}).get('weapon')
                break
        
        if not target_attachment or not target_attachment.get('image'):
            await query.answer(t('attachment.not_found', lang), show_alert=True)
            return
        
        # ارسال اتچمنت
        from config.config import WEAPON_CATEGORIES
        cat_name_en = t(f"category.{target_category}", lang)
        priority_emoji = self._get_priority_emoji_for_suggested(target_attachment.get('priority', 500))
        
        caption = (
            f"{priority_emoji} **{target_weapon}** ({cat_name_en})\n"
            f"📎 {target_attachment['name']}\n"
            f"{t('attachment.code', lang)}: `{target_attachment['code']}`\n"
            f"{mode_name}"
        )
        
        # اضافه کردن دلیل پیشنهاد
        reason = target_attachment.get('reason')
        if reason:
            caption += f"\n💭 {reason}"
        
        # دریافت آمار بازخورد
        stats = self.db.get_attachment_stats(att_id, period='all')
        like_count = stats.get('like_count', 0)
        dislike_count = stats.get('dislike_count', 0)
        
        # Track view
        self.db.track_attachment_view(query.from_user.id, att_id)
        
        # ساخت keyboard با دکمه‌های بازخورد
        keyboard = [
            [
                InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
            ],
            [InlineKeyboardButton(t('attachment.copy_code', lang), callback_data=f"att_copy_{att_id}")],
            [InlineKeyboardButton(t('attachment.feedback', lang), callback_data=f"att_fb_{att_id}")],
            [InlineKeyboardButton(t('suggested.more_for_weapon', lang), 
                                 callback_data=f"sugg_wpn_{mode}_{target_category}__{target_weapon}")],
            [InlineKeyboardButton(t('suggested.back_to_weapons', lang), callback_data=f"suggested_mode_{mode}")],
            [InlineKeyboardButton(t('menu.buttons.home', lang), callback_data="main_menu")]
        ]
        
        await query.message.reply_photo(
            photo=target_attachment['image'],
            caption=caption[:1024],
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        await safe_edit_message_text(
            query,
            t('success.generic', lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data=f"sugg_wpn_{mode}_{target_category}__{target_weapon}")]
            ])
        )
    
    def _get_priority_emoji_for_suggested(self, priority: int) -> str:
        """دریافت emoji مناسب برای اولویت"""
        if priority <= 100:
            return "🔥"  # اولویت خیلی بالا
        elif priority <= 300:
            return "⭐"  # اولویت بالا
        elif priority <= 500:
            return "💫"  # اولویت متوسط
        else:
            return "✨"  # اولویت پایین
    
    @require_channel_membership
    @log_user_action("suggested_list_with_mode")
    async def suggested_list_with_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیست اتچمنت‌های پیشنهادی با mode مشخص شده"""
        query = update.callback_query
        await query.answer()
        
        # استخراج mode از callback_data: suggested_list_mode_{mode}
        mode = query.data.replace("suggested_list_mode_", "")
        context.user_data['suggested_list_mode'] = mode
        
        # دریافت اتچمنت‌های پیشنهادی
        lang = get_user_lang(update, context, self.db) or 'fa'
        items = self.db.get_suggested_ranked(mode)
        mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_btn', lang)}"
        
        if not items:
            await safe_edit_message_text(
                query,
                t('attachment.none', lang),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="suggested_attachments")],
                    [InlineKeyboardButton(t('menu.buttons.home', lang), callback_data="main_menu")]
                ])
            )
            return
        
        # ساخت صفحه اول
        text, markup, page = self._suggested_build_page(items, 1, mode, lang)
        context.user_data['suggested_cache'] = items
        context.user_data['suggested_page'] = 1
        
        await safe_edit_message_text(query, text, reply_markup=markup, parse_mode='Markdown')
    
    def _suggested_build_page(self, items: list, page: int, mode: str, lang: str) -> Tuple[str, InlineKeyboardMarkup, int]:
        """ساخت صفحه لیست اتچمنت‌های پیشنهادی"""
        total_items = len(items)
        total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
        
        # محدود کردن صفحه
        page = max(1, min(page, total_pages))
        
        # محاسبه شروع و پایان
        start_idx = (page - 1) * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
        page_items = items[start_idx:end_idx]
        
        # ساخت متن
        mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_btn', lang)}"
        text = t('suggested.attachments_title', lang) + f" ({mode_name})\n"
        text += t('pagination.page_of', lang, page=page, total=total_pages) + " | " + t('pagination.showing_range', lang, start=start_idx + 1, end=end_idx, total=total_items) + "\n"
        text += "➖➖➖➖➖➖➖➖➖\n\n"
        
        for idx, item in enumerate(page_items, start=start_idx + 1):
            category = (item or {}).get('category')
            weapon = (item or {}).get('weapon')
            attachment = (item or {}).get('attachment', {})
            cat_name_en = t(f"category.{category}", lang)
            priority_emoji = self._get_priority_emoji_for_suggested(attachment.get('priority', 500))
            
            text += f"{idx}. {priority_emoji} **{weapon}** ({cat_name_en})\n"
            text += f"   📎 {attachment.get('name')}\n"
            text += f"   {t('attachment.code', lang)}: `{attachment.get('code')}`\n"
            
            # نمایش آمار feedback
            likes = attachment.get('likes', 0)
            dislikes = attachment.get('dislikes', 0)
            pop_score = attachment.get('pop_score', 0)
            
            if likes > 0 or dislikes > 0:
                text += f"   👍 {likes} | 👎 {dislikes} | 📊 {t('common.score', lang)}: {pop_score}\n"
            
            # نمایش دلیل پیشنهاد
            reason = attachment.get('reason')
            if reason:
                text += f"   💭 {reason}\n"
            
            text += "\n"
        
        # ساخت کیبورد
        keyboard = []
        
        # دکمه‌های navigation
        if total_pages > 1:
            nav = []
            if page > 1:
                nav.append(InlineKeyboardButton(t('nav.prev', lang), callback_data=f"sugglist_page_{page-1}"))
            nav.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
            if page < total_pages:
                nav.append(InlineKeyboardButton(t('nav.next', lang), callback_data=f"sugglist_page_{page+1}"))
            keyboard.append(nav)
        
        # دکمه‌های بازگشت
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="suggested_attachments")])
        keyboard.append([InlineKeyboardButton(t('menu.buttons.home', lang), callback_data="main_menu")])
        
        return text, InlineKeyboardMarkup(keyboard), page
    
    @require_channel_membership
    @log_user_action("suggested_list_page_navigation")
    async def suggested_list_page_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """مدیریت navigation بین صفحات لیست پیشنهادی‌ها"""
        query = update.callback_query
        await query.answer()
        
        # دریافت cache و mode ذخیره شده
        items = context.user_data.get('suggested_cache')
        mode = context.user_data.get('suggested_list_mode')
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if not items:
            # اگر cache نبود، دوباره بگیر
            items = self.db.get_suggested_ranked(mode)
            context.user_data['suggested_cache'] = items
        
        # استخراج شماره صفحه
        page = 1
        if query.data.startswith('sugglist_page_'):
            try:
                page = int(query.data.replace('sugglist_page_', ''))
            except ValueError:
                page = 1
        
        text, markup, page = self._suggested_build_page(items, page, mode, lang)
        context.user_data['suggested_page'] = page
        await safe_edit_message_text(query, text, reply_markup=markup, parse_mode='Markdown')
