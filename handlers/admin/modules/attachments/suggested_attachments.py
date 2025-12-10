"""
ماژول مدیریت اتچمنت‌های پیشنهادی
مسئول: مدیریت پیشنهادات کاربران
"""

import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.config import WEAPON_CATEGORIES, GAME_MODES
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import (
    MANAGE_SUGGESTED_MENU, MANAGE_SUGGESTED_MODE, MANAGE_SUGGESTED_ADD,
    MANAGE_SUGGESTED_ADD_CATEGORY, MANAGE_SUGGESTED_ADD_WEAPON,
    MANAGE_SUGGESTED_ADD_ATTACHMENT, MANAGE_SUGGESTED_ADD_PRIORITY,
    MANAGE_SUGGESTED_ADD_REASON, MANAGE_SUGGESTED_REMOVE_SELECT
)
from utils.logger import log_admin_action, log_performance, performance_logger
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text


class SuggestedAttachmentsHandler(BaseAdminHandler):
    """Handler برای مدیریت اتچمنت‌های پیشنهادی"""
    
    @log_admin_action("manage_suggested_menu")
    async def manage_suggested_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی مدیریت اتچمنت‌های پیشنهادی"""
        start_ts = time.perf_counter()
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # بررسی دسترسی
        from core.security.role_manager import Permission
        user_permissions = self.role_manager.get_user_permissions(query.from_user.id)
        
        if Permission.MANAGE_SUGGESTED_ATTACHMENTS not in user_permissions:
            duration = time.perf_counter() - start_ts
            log_performance(performance_logger, "Suggested.manage_suggested_menu(no_permission)", duration, threshold=0.2)
            await query.answer(t("common.no_permission", lang), show_alert=True)
            from handlers.admin.admin_states import ADMIN_MENU
            return ADMIN_MENU
        
        # دریافت تعداد اتچمنت‌های پیشنهادی (با اندازه‌گیری زمان هر فراخوانی)
        t0 = time.perf_counter()
        br_count = self.db.get_suggested_count('br')
        log_performance(performance_logger, "DB.get_suggested_count(br)", time.perf_counter() - t0, threshold=0.1)
        t1 = time.perf_counter()
        mp_count = self.db.get_suggested_count('mp')
        log_performance(performance_logger, "DB.get_suggested_count(mp)", time.perf_counter() - t1, threshold=0.1)
        total_count = br_count + mp_count
        
        text = (
            t("admin.suggested.menu.title", lang) + "\n\n"
            + t("admin.suggested.menu.status", lang) + "\n"
            + t("admin.suggested.menu.br", lang, n=br_count) + "\n"
            + t("admin.suggested.menu.mp", lang, n=mp_count) + "\n"
            + t("admin.suggested.menu.total", lang, n=total_count) + "\n\n"
            + t("admin.suggested.menu.prompt", lang)
        )
        
        keyboard = [
            [
                InlineKeyboardButton(t("admin.suggested.buttons.add", lang), callback_data="msug_add"),
                InlineKeyboardButton(t("admin.suggested.buttons.remove", lang), callback_data="msug_remove")
            ],
            [InlineKeyboardButton(t("admin.suggested.buttons.view_list", lang), callback_data="msug_view")],
            [InlineKeyboardButton(t("admin.suggested.buttons.analytics", lang), callback_data="analytics_suggested")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")]
        ]
        
        tg0 = time.perf_counter()
        await safe_edit_message_text(
            query,
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        log_performance(performance_logger, "TG.edit_message_text(Suggested.manage_suggested_menu)", time.perf_counter() - tg0, threshold=0.25)
        
        duration = time.perf_counter() - start_ts
        log_performance(performance_logger, "Suggested.manage_suggested_menu(total)", duration, threshold=0.3)
        return MANAGE_SUGGESTED_MENU

    # ========== Suggested Analytics ==========
    @log_admin_action("suggested_analytics_menu")
    async def suggested_analytics_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی آنالیتیکس مخصوص اتچمنت‌های پیشنهادی"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        br_count = self.db.get_suggested_count('br')
        mp_count = self.db.get_suggested_count('mp')
        total = br_count + mp_count
        
        text = (
            t("admin.suggested.analytics.title", lang) + "\n\n"
            + t("admin.suggested.analytics.summary", lang, total=total, br=br_count, mp=mp_count) + "\n\n"
            + t("admin.suggested.analytics.prompt", lang)
        )
        
        keyboard = [
            [InlineKeyboardButton(t("admin.suggested.analytics.buttons.trending", lang), callback_data="analytics_sugg_trending")],
            [InlineKeyboardButton(t("admin.suggested.analytics.buttons.underperforming", lang), callback_data="analytics_sugg_underperforming")],
            [InlineKeyboardButton(t("admin.suggested.analytics.buttons.weapon_stats", lang), callback_data="analytics_sugg_weapon_stats")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_manage_suggested")]
        ]
        
        await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return MANAGE_SUGGESTED_MENU
    
    @log_admin_action("analytics_sugg_trending")
    async def analytics_sugg_trending(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش ترندینگ پیشنهادی‌ها (ترکیب BR و MP بر اساس PopScore)"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        items = []
        for mode in ('br', 'mp'):
            try:
                items.extend(self.db.get_suggested_ranked(mode))
            except Exception:
                pass
        
        if not items:
            text = t('attachment.none', lang)
        else:
            # مرتب‌سازی بر اساس pop_score نزولی
            rows = []
            for item in items:
                att = (item or {}).get('attachment', {})
                rows.append({
                    'mode': (item or {}).get('mode'),
                    'weapon': (item or {}).get('weapon'),
                    'name': att.get('name'),
                    'code': att.get('code'),
                    'likes': att.get('likes', 0),
                    'dislikes': att.get('dislikes', 0),
                    'views': att.get('views', 0),
                    'pop': att.get('pop_score', 0)
                })
            rows.sort(key=lambda r: r['pop'], reverse=True)
            rows = rows[:10]
            
            text = t("admin.suggested.analytics.trending.title", lang) + "\n\n"
            for i, r in enumerate(rows, 1):
                icon = "🪂" if r['mode'] == 'br' else "🎮"
                text += f"{i}. {icon} {r['weapon']} — {r['name']}\n"
                text += f"   👍 {r['likes']} | 👎 {r['dislikes']} | 👁 {r['views']} | 📊 {r['pop']}\n\n"
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="analytics_suggested")]]
        await safe_edit_message_text(query, text[:4096], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return MANAGE_SUGGESTED_MENU
    
    @log_admin_action("analytics_sugg_underperforming")
    async def analytics_sugg_underperforming(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش اتچمنت‌های پیشنهادی کم‌اثر (نمره منفی یا بازدید پایین)"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        items = []
        for mode in ('br', 'mp'):
            try:
                items.extend(self.db.get_suggested_ranked(mode))
            except Exception:
                pass
        
        under = []
        for item in items:
            att = (item or {}).get('attachment', {})
            likes = att.get('likes', 0)
            dislikes = att.get('dislikes', 0)
            views = att.get('views', 0)
            if (likes - dislikes) <= 0 or views < 20:
                under.append(((item or {}).get('weapon'), (item or {}).get('mode'), att))
        
        text = t("admin.suggested.analytics.underperforming.title", lang) + "\n\n"
        keyboard = []
        if not under:
            text += t("common.no_items", lang)
        else:
            # محدود به 10 مورد
            for i, (weapon, mode, att) in enumerate(under[:10], 1):
                icon = "🪂" if mode == 'br' else "🎮"
                name = att.get('name')
                code = att.get('code')
                likes = att.get('likes', 0)
                dislikes = att.get('dislikes', 0)
                views = att.get('views', 0)
                text += f"{i}. {icon} {weapon} — {name}\n"
                text += f"   🔤 `{code}` | 👍 {likes} | 👎 {dislikes} | 👁 {views}\n"
                # دکمه حذف از پیشنهادی‌ها
                keyboard.append([InlineKeyboardButton(
                    t("admin.suggested.buttons.remove_from_suggested", lang),
                    callback_data=f"msugr_{mode}_{att.get('id')}"
                )])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="analytics_suggested")])
        await safe_edit_message_text(query, text[:4096], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return MANAGE_SUGGESTED_MENU
    
    @log_admin_action("analytics_sugg_weapon_stats")
    async def analytics_sugg_weapon_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش آمار پیشنهادی‌ها به تفکیک سلاح"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        items = []
        for mode in ('br', 'mp'):
            try:
                items.extend(self.db.get_suggested_ranked(mode))
            except Exception:
                pass
        
        stats = {}
        for item in items:
            att = (item or {}).get('attachment', {})
            weapon = (item or {}).get('weapon')
            s = stats.setdefault(weapon, {'count': 0, 'likes': 0, 'dislikes': 0, 'views': 0})
            s['count'] += 1
            s['likes'] += att.get('likes', 0)
            s['dislikes'] += att.get('dislikes', 0)
            s['views'] += att.get('views', 0)
        
        text = t("admin.suggested.analytics.weapon_stats.title", lang) + "\n\n"
        if not stats:
            text += t("common.no_data", lang)
        else:
            # مرتب‌سازی بر اساس مجموع views
            ranked = sorted(stats.items(), key=lambda kv: kv[1]['views'], reverse=True)[:10]
            for i, (weapon, s) in enumerate(ranked, 1):
                text += f"{i}. {weapon}\n"
                text += f"   📎 {s['count']} {t('unit.attachment', lang)} | 👍 {s['likes']} | 👎 {s['dislikes']} | 👁 {s['views']}\n\n"
        
        keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="analytics_suggested")]]
        await query.edit_message_text(text[:4096], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return MANAGE_SUGGESTED_MENU
    
    @log_admin_action("suggested_add_start")
    async def suggested_add_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع افزودن اتچمنت پیشنهادی - انتخاب mode"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پاک کردن navigation stack برای شروع flow جدید
        self._clear_navigation(context)
        
        # اضافه کردن state اولیه برای برگشت
        self._push_navigation(context, MANAGE_SUGGESTED_MENU, {})
        
        user_id = query.from_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        
        keyboard = []
        # دکمه‌های mode به صورت دو ستونه در یک ردیف
        mode_row = []
        if 'mp' in allowed_modes:
            mode_row.append(InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="msugm_mp"))
        if 'br' in allowed_modes:
            mode_row.append(InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="msugm_br"))
        if mode_row:
            keyboard.append(mode_row)
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_manage_suggested")])
        
        await safe_edit_message_text(
            query,
            t("admin.suggested.add.choose_mode", lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MANAGE_SUGGESTED_MODE
    
    @log_admin_action("suggested_mode_selected")
    async def suggested_mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب mode و نمایش دسته‌ها"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # ذخیره state فعلی
        self._push_navigation(context, MANAGE_SUGGESTED_MODE, {})
        
        mode = query.data.replace("msugm_", "")
        context.user_data['suggested_mode'] = mode
        
        # فیلتر کردن دسته‌های فعال برای mode انتخاب شده
        from config.config import build_category_keyboard, is_category_enabled
        active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() if is_category_enabled(k, mode)}
        
        if not active_categories:
            mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}"
            await safe_edit_message_text(
                query,
                f"📍 {mode_name}\n\n" + t('admin.suggested.no_active_categories_hint', lang)
            )
            return MANAGE_SUGGESTED_MODE
        
        # ساخت کیبورد 2 ستونی برای دسته‌های فعال
        keyboard = build_category_keyboard(active_categories, "msugc_")
        # استفاده از helper برای consistency
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}"
        await safe_edit_message_text(
            query,
            t('admin.suggested.select_category', lang, mode_name=mode_name),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MANAGE_SUGGESTED_ADD_CATEGORY
    
    @log_admin_action("suggested_category_selected")
    async def suggested_category_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب دسته و نمایش سلاح‌ها"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # بررسی دکمه‌های خاص
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            return await self.handle_navigation_back(update, context)
        
        # ذخیره state فعلی
        self._push_navigation(context, MANAGE_SUGGESTED_ADD_CATEGORY, {
            'suggested_mode': context.user_data.get('suggested_mode')
        })
        
        category = query.data.replace("msugc_", "")
        context.user_data['suggested_category'] = category
        
        weapons = self.db.get_weapons_in_category(category)
        if not weapons:
            await query.answer(t("admin.no_weapons_in_category", lang), show_alert=True)
            return MANAGE_SUGGESTED_ADD_CATEGORY
        
        keyboard = self._make_weapon_keyboard(weapons, "msugw_", category)
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        await safe_edit_message_text(
            query,
            t('admin.suggested.select_weapon', lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MANAGE_SUGGESTED_ADD_WEAPON
    
    @log_admin_action("suggested_weapon_selected")
    async def suggested_weapon_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب سلاح و نمایش اتچمنت‌ها"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # بررسی دکمه‌های خاص
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            return await self.handle_navigation_back(update, context)
        
        # ذخیره state فعلی
        self._push_navigation(context, MANAGE_SUGGESTED_ADD_WEAPON, {
            'suggested_mode': context.user_data.get('suggested_mode'),
            'suggested_category': context.user_data.get('suggested_category')
        })
        
        weapon = query.data.replace("msugw_", "")
        context.user_data['suggested_weapon'] = weapon
        
        category = context.user_data['suggested_category']
        mode = context.user_data['suggested_mode']
        
        attachments = self.db.get_all_attachments(category, weapon, mode)
        if not attachments:
            await query.answer(t('attachment.none', lang), show_alert=True)
            return MANAGE_SUGGESTED_ADD_WEAPON
        
        sugg_items = self.db.get_suggested_attachments(mode)
        suggested_ids = set()
        for it in sugg_items:
            att = (it or {}).get('attachment', {})
            att_id = att.get('id')
            if att_id:
                suggested_ids.add(att_id)
        
        keyboard = []
        for att in attachments:
            status = "✅ " if att.get('id') in suggested_ids else ""
            keyboard.append([InlineKeyboardButton(
                f"{status}{att['name']}",
                callback_data=f"msuga_{att['id']}"
            )])
        
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        await safe_edit_message_text(
            query,
            t('admin.suggested.select_attachment', lang) + "\n\n" + t('admin.suggested.already_suggested_legend', lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MANAGE_SUGGESTED_ADD_ATTACHMENT
    
    @log_admin_action("suggested_attachment_selected")
    async def suggested_attachment_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """افزودن اتچمنت به لیست پیشنهادی"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # بررسی دکمه‌های خاص
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            return await self.handle_navigation_back(update, context)
        
        # اینجا push نمی‌کنیم چون بعد از انتخاب مستقیم به menu می‌ریم
        att_id = int(query.data.replace("msuga_", ""))
        mode = context.user_data['suggested_mode']
        admin_id = query.from_user.id
        
        # بررسی تکراری نبودن
        if self.db.is_attachment_suggested(att_id, mode):
            # فقط نمایش alert بدون تغییر صفحه
            await query.answer(t('admin.suggested.already_suggested_alert', lang), show_alert=True)
            return MANAGE_SUGGESTED_ADD_ATTACHMENT
        
        await query.answer()
        
        # افزودن به دیتابیس
        success = self.db.add_suggested_attachment(
            attachment_id=att_id,
            mode=mode,
            priority=500,  # اولویت پیش‌فرض
            reason=None,
            added_by=admin_id
        )
        
        if success:
            await safe_edit_message_text(
                query,
                t('admin.suggested.add.success', lang) + "\n\n"
                f"📍 {t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t('admin.suggested.buttons.add_more', lang), callback_data="msug_add")],
                    [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="admin_manage_suggested")]
                ])
            )
        else:
            await safe_edit_message_text(query, t('admin.suggested.add.error', lang))
        
        return MANAGE_SUGGESTED_MENU
    
    @log_admin_action("suggested_remove_start")
    async def suggested_remove_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع حذف اتچمنت پیشنهادی"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        keyboard = [
            [
                InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="msugm_remove_mp"),
                InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="msugm_remove_br")
            ],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_manage_suggested")]
        ]
        
        await safe_edit_message_text(
            query,
            t('admin.suggested.remove.choose_mode', lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return MANAGE_SUGGESTED_MODE
    
    @log_admin_action("suggested_remove_mode_selected")
    async def suggested_remove_mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب mode برای حذف و نمایش لیست"""
        start_ts = time.perf_counter()
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        mode = query.data.replace("msugm_remove_", "")
        t0 = time.perf_counter()
        items = self.db.get_suggested_attachments(mode)
        log_performance(performance_logger, f"DB.get_suggested_attachments({mode})", time.perf_counter() - t0, threshold=0.2)
        
        if not items:
            await safe_edit_message_text(
                query,
                t('admin.suggested.remove.empty_in_mode', lang, mode_name=f"{t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}"),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="msug_remove")]
                ])
            )
            duration = time.perf_counter() - start_ts
            log_performance(performance_logger, "Suggested.remove_mode_selected(empty)", duration, threshold=0.3)
            return MANAGE_SUGGESTED_MODE
        
        keyboard = []
        # items format: (category, weapon, mode, attachment_dict)
        for item in items[:20]:  # نمایش 20 مورد اول
            att = (item or {}).get('attachment', {})
            weapon = (item or {}).get('weapon')
            att_id = att.get('id')
            if not att_id:
                continue
            keyboard.append([InlineKeyboardButton(
                f"{weapon} - {att.get('name', '')}",
                callback_data=f"msugr_{mode}_{att_id}"
            )])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="msug_remove")])
        
        edit_ts = time.perf_counter()
        await safe_edit_message_text(
            query,
            t('admin.suggested.remove.list_prompt', lang, mode_name=f"{t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}"),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        log_performance(performance_logger, f"TG.edit_message_text(Suggested.remove_mode_selected:{mode})", time.perf_counter() - edit_ts, threshold=0.25)
        
        duration = time.perf_counter() - start_ts
        log_performance(performance_logger, "Suggested.remove_mode_selected(total)", duration, threshold=0.4)
        return MANAGE_SUGGESTED_REMOVE_SELECT
    
    @log_admin_action("suggested_delete_confirmed")
    async def suggested_delete_confirmed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """حذف اتچمنت از لیست پیشنهادی"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # استخراج mode و id: msugr_{mode}_{att_id}
        parts = query.data.replace("msugr_", "").split("_", 1)
        mode = parts[0]
        att_id = int(parts[1])
        
        if self.db.remove_suggested_attachment(att_id, mode):
            await safe_edit_message_text(
                query,
                t('admin.suggested.delete.success', lang),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_manage_suggested")]
                ])
            )
        else:
            await safe_edit_message_text(query, t('admin.suggested.delete.error', lang))
        
        return MANAGE_SUGGESTED_MENU
    
    @log_admin_action("suggested_view_list")
    async def suggested_view_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیست اتچمنت‌های پیشنهادی"""
        start_ts = time.perf_counter()
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # دریافت لیست اتچمنت‌های پیشنهادی
        t0 = time.perf_counter()
        br_items = self.db.get_suggested_attachments('br')
        log_performance(performance_logger, "DB.get_suggested_attachments(br)", time.perf_counter() - t0, threshold=0.2)
        t1 = time.perf_counter()
        mp_items = self.db.get_suggested_attachments('mp')
        log_performance(performance_logger, "DB.get_suggested_attachments(mp)", time.perf_counter() - t1, threshold=0.2)
        
        text = t("admin.suggested.view_list.title", lang) + "\n\n"
        
        if br_items:
            text += t("admin.suggested.view_list.br", lang) + "\n"
            for item in br_items[:10]:
                weapon = (item or {}).get('weapon')
                att = (item or {}).get('attachment', {})
                text += f"• {weapon}: {att.get('name', '')}\n"
            if len(br_items) > 10:
                text += t("common.items_other_count", lang, n=(len(br_items) - 10)) + "\n"
            text += "\n"
        
        if mp_items:
            text += t("admin.suggested.view_list.mp", lang) + "\n"
            for item in mp_items[:10]:
                weapon = (item or {}).get('weapon')
                att = (item or {}).get('attachment', {})
                text += f"• {weapon}: {att.get('name', '')}\n"
            if len(mp_items) > 10:
                text += t("common.items_other_count", lang, n=(len(mp_items) - 10)) + "\n"
        
        if not br_items and not mp_items:
            text += t("admin.suggested.none", lang)
        
        keyboard = [
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_manage_suggested")]
        ]
        
        v_ts = time.perf_counter()
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        log_performance(performance_logger, "TG.edit_message_text(Suggested.view_list)", time.perf_counter() - v_ts, threshold=0.25)
        
        return MANAGE_SUGGESTED_MENU
    
    async def _rebuild_state_screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: int):
        """بازسازی صفحه برای هر state"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if state == MANAGE_SUGGESTED_MENU:
            # بازگشت به منوی اصلی
            br_count = self.db.get_suggested_count('br')
            mp_count = self.db.get_suggested_count('mp')
            total_count = br_count + mp_count
            
            text = (
                t("admin.suggested.menu.title", lang) + "\n\n"
                + t("admin.suggested.menu.status", lang) + "\n"
                + t("admin.suggested.menu.br", lang, n=br_count) + "\n"
                + t("admin.suggested.menu.mp", lang, n=mp_count) + "\n"
                + t("admin.suggested.menu.total", lang, n=total_count) + "\n\n"
                + t("admin.suggested.menu.prompt", lang)
            )
            
            keyboard = [
                [
                    InlineKeyboardButton(t("admin.suggested.buttons.add", lang), callback_data="msug_add"),
                    InlineKeyboardButton(t("admin.suggested.buttons.remove", lang), callback_data="msug_remove")
                ],
                [InlineKeyboardButton(t("admin.suggested.buttons.view_list", lang), callback_data="msug_view")],
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_menu_return")]
            ]
            
            await safe_edit_message_text(
                query,
                text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif state == MANAGE_SUGGESTED_MODE:
            # بازگشت به انتخاب mode
            user_id = query.from_user.id
            allowed_modes = self.role_manager.get_mode_permissions(user_id)
            
            keyboard = []
            # دکمه‌های mode به صورت دو ستونه
            mode_row = []
            if 'mp' in allowed_modes:
                mode_row.append(InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="msugm_mp"))
            if 'br' in allowed_modes:
                mode_row.append(InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="msugm_br"))
            if mode_row:
                keyboard.append(mode_row)
            keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_manage_suggested")])
            
            await safe_edit_message_text(
                query,
                t("admin.suggested.add.choose_mode", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif state == MANAGE_SUGGESTED_ADD_CATEGORY:
            # بازگشت به لیست دسته‌ها
            mode = context.user_data.get('suggested_mode')
            mode_name = f"{t('mode.label', lang)}: {t(f'mode.{mode}_short', lang)}"
            
            # نمایش فقط دسته‌های فعال برای mode انتخاب شده و با کیبورد استاندارد
            from config.config import build_category_keyboard, is_category_enabled
            active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() if is_category_enabled(k, mode)}
            keyboard = build_category_keyboard(active_categories, "msugc_")
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            await safe_edit_message_text(
                query,
                t('admin.suggested.select_category', lang, mode_name=mode_name),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif state == MANAGE_SUGGESTED_ADD_WEAPON:
            # بازگشت به لیست سلاح‌ها
            category = context.user_data.get('suggested_category')
            if category:
                weapons = self.db.get_weapons_in_category(category)
                keyboard = self._make_weapon_keyboard(weapons, "msugw_", category)
                self._add_back_cancel_buttons(keyboard, show_back=True)
                
                await safe_edit_message_text(
                    query,
                    t('admin.suggested.select_weapon', lang),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        
        elif state == MANAGE_SUGGESTED_ADD_ATTACHMENT:
            # بازگشت به لیست اتچمنت‌ها
            category = context.user_data.get('suggested_category')
            weapon = context.user_data.get('suggested_weapon')
            mode = context.user_data.get('suggested_mode')
            
            attachments = self.db.get_all_attachments(category, weapon, mode)
            sugg_items = self.db.get_suggested_attachments(mode)
            suggested_ids = set()
            for it in sugg_items:
                att_d = (it or {}).get('attachment', {})
                att_id = att_d.get('id')
                if att_id:
                    suggested_ids.add(att_id)
            keyboard = []
            for att in attachments:
                status = "✅ " if att.get('id') in suggested_ids else ""
                keyboard.append([InlineKeyboardButton(
                    f"{status}{att['name']}",
                    callback_data=f"msuga_{att['id']}"
                )])
            
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            await safe_edit_message_text(
                query,
                t('admin.suggested.select_attachment', lang) + "\n\n" + t('admin.suggested.already_suggested_legend', lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
