"""
ماژول حذف اتچمنت (REFACTORED)
مسئول: حذف اتچمنت با انتخاب از لیست، پشتیبانی از ID-based selection

ترتیب جدید: Mode → Category → Weapon → Select
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from config.config import WEAPON_CATEGORIES, GAME_MODES
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import (
    DELETE_ATTACHMENT_MODE, DELETE_ATTACHMENT_CATEGORY,
    DELETE_ATTACHMENT_WEAPON, DELETE_ATTACHMENT_SELECT
)
from utils.logger import log_admin_action
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text


class DeleteAttachmentHandler(BaseAdminHandler):
    """Handler برای حذف اتچمنت - Mode First Flow"""
    
    @log_admin_action("delete_attachment_start")
    async def delete_attachment_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع فرآیند حذف اتچمنت - انتخاب Mode"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پاک کردن navigation stack
        self._clear_navigation(context)
        
        # فیلتر کردن modeها بر اساس دسترسی کاربر
        user_id = update.effective_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        
        # اگر هیچ دسترسی ندارد
        if not allowed_modes:
            await safe_edit_message_text(query, t("common.no_permission", lang))
            return await self.admin_menu_return(update, context)
        
        # انتخاب Mode (BR/MP) - فقط modeهای مجاز
        keyboard = []
        mode_buttons = []
        # ترتیب: BR راست، MP چپ
        if 'br' in allowed_modes:
            mode_buttons.append(InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="dam_br"))
        if 'mp' in allowed_modes:
            mode_buttons.append(InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="dam_mp"))
        if mode_buttons:
            keyboard.append(mode_buttons)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await safe_edit_message_text(query, t("admin.delete.mode.prompt", lang), reply_markup=reply_markup)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        
        return DELETE_ATTACHMENT_MODE
    
    @log_admin_action("delete_attachment_mode_selected")
    async def delete_attachment_mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب Mode (BR/MP) برای حذف - سپس نمایش Categories"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست modeها
            return await self.delete_attachment_start(update, context)
        
        mode = query.data.replace("dam_", "")  # br یا mp
        
        # بررسی دسترسی به mode انتخاب شده
        user_id = update.effective_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        
        if mode not in allowed_modes:
            await query.answer(t("common.no_permission", lang), show_alert=True)
            return DELETE_ATTACHMENT_MODE
        
        # ذخیره state فعلی
        self._push_navigation(context, DELETE_ATTACHMENT_MODE, {})
        
        context.user_data['del_att_mode'] = mode
        mode_name = GAME_MODES.get(mode, mode)
        
        # فیلتر کردن دسته‌های فعال برای mode انتخاب شده
        from config.config import build_category_keyboard, is_category_enabled
        active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() if is_category_enabled(k, mode)}
        
        if not active_categories:
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.attach.category.none_active", lang) + "\n" + t("admin.attach.category.enable_hint", lang)
            )
            return DELETE_ATTACHMENT_MODE
        
        # ساخت کیبورد 2 ستونی برای Categories فعال
        keyboard = build_category_keyboard(active_categories, "dac_")
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.weapons.choose_category", lang),
                reply_markup=reply_markup
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        
        return DELETE_ATTACHMENT_CATEGORY
    
    @log_admin_action("delete_attachment_category_selected")
    async def delete_attachment_category_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب دسته برای حذف اتچمنت - سپس نمایش Weapons"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست modeها
            context.user_data.pop('del_att_category', None)
            return await self.delete_attachment_start(update, context)
        
        # ذخیره state فعلی
        self._push_navigation(context, DELETE_ATTACHMENT_CATEGORY, {
            'del_att_mode': context.user_data.get('del_att_mode')
        })
        
        category = query.data.replace("dac_", "")
        context.user_data['del_att_category'] = category
        
        weapons = self.db.get_weapons_in_category(category)
        mode = context.user_data.get('del_att_mode', 'br')
        mode_name = GAME_MODES.get(mode, mode)
        
        if not weapons:
            try:
                await safe_edit_message_text(
                    query,
                    t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("admin.weapons.none_in_category", lang)
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                else:
                    raise
            return await self.admin_menu_return(update, context)
        
        # ساخت keyboard با تعداد ستون‌های متغیر برای سلاح‌ها
        keyboard = self._make_weapon_keyboard(weapons, "daw_", category)
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await safe_edit_message_text(
                query,
                t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("weapon.choose", lang),
                reply_markup=reply_markup
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        
        return DELETE_ATTACHMENT_WEAPON
    
    @log_admin_action("delete_attachment_weapon_selected")
    async def delete_attachment_weapon_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب سلاح برای حذف - مستقیم نمایش لیست Attachments"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست دسته‌ها
            context.user_data.pop('del_att_weapon', None)
            mode = context.user_data.get('del_att_mode', 'br')
            mode_name = GAME_MODES.get(mode, mode)
            
            from config.config import build_category_keyboard, is_category_enabled
            active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() if is_category_enabled(k, mode)}
            keyboard = build_category_keyboard(active_categories, "dac_")
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            try:
                await safe_edit_message_text(
                    query,
                    t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.weapons.choose_category", lang),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                else:
                    raise
            return DELETE_ATTACHMENT_CATEGORY
        
        # ذخیره state فعلی
        self._push_navigation(context, DELETE_ATTACHMENT_WEAPON, {
            'del_att_mode': context.user_data.get('del_att_mode'),
            'del_att_category': context.user_data.get('del_att_category')
        })
        
        weapon = query.data.replace("daw_", "")
        context.user_data['del_att_weapon'] = weapon
        
        # دریافت اطلاعات برای نمایش
        category = context.user_data['del_att_category']
        mode = context.user_data.get('del_att_mode', 'br')
        mode_name = GAME_MODES.get(mode, mode)
        
        # مستقیماً لیست اتچمنت‌ها را برای حذف نمایش بده
        attachments = self.db.get_all_attachments(category, weapon, mode=mode)
        
        if not attachments:
            # ساخت کیبورد با دکمه بازگشت به لیست سلاح‌ها
            keyboard = [
                [InlineKeyboardButton(t("admin.delete.buttons.back_to_weapons", lang), callback_data=f"dac_{category}")],
                [InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await safe_edit_message_text(
                    query,
                    t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n" + t("attachment.none", lang),
                    reply_markup=reply_markup
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                else:
                    raise
            # باقی ماندن در همین state تا دکمه بازگشت زده شود
            return DELETE_ATTACHMENT_CATEGORY
        
        keyboard = []
        for att in attachments:
            # استفاده از ID به جای code در callback_data - فقط name نمایش داده میشه
            keyboard.append([InlineKeyboardButton(
                f"🗑️ {att['name']}", 
                callback_data=f"delatt_id_{att['id']}"
            )])
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        try:
            await safe_edit_message_text(
                query,
                t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n" + t("admin.delete.choose_attachment", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        return DELETE_ATTACHMENT_SELECT
    
    @log_admin_action("delete_attachment_code_selected")
    async def delete_attachment_code_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """حذف با انتخاب از لیست (با ID)"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            return await self.handle_navigation_back(update, context)
        
        # دریافت ID از callback_data
        att_id = int(query.data.replace("delatt_id_", ""))
        category = context.user_data['del_att_category']
        weapon = context.user_data['del_att_weapon']
        mode = context.user_data.get('del_att_mode', 'br')
        mode_name = GAME_MODES.get(mode, mode)
        
        # پیدا کردن اتچمنت با ID برای گرفتن نام و کد
        att_to_delete = None
        try:
            for att in self.db.get_all_attachments(category, weapon, mode=mode):
                if att.get('id') == att_id:
                    att_to_delete = att
                    break
        except Exception:
            pass
        
        if not att_to_delete:
            try:
                await safe_edit_message_text(query, t("attachment.not_found", lang))
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                else:
                    raise
            return await self.admin_menu_return(update, context)
        
        code = att_to_delete['code']
        name = att_to_delete['name']
        
        if self.db.delete_attachment(category, weapon, code, mode=mode):
            try:
                await safe_edit_message_text(
                    query,
                    t("admin.delete.success", lang, name=name, mode=mode_name) + "\n\n" + t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + f" > {weapon}"
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                else:
                    raise
            # invalidate related caches
            try:
                from core.cache.cache_manager import get_cache
                cache = get_cache()
                cache.invalidate_pattern(f"_{category}_{weapon}")
                cache.invalidate_pattern("get_all_attachments")
                cache.invalidate_pattern("get_weapon_attachments")
                cache.invalidate_pattern("get_top_attachments")
                # حذف کش شمارش دسته‌ها (در صورت تغییر مجموعه سلاح‌ها از طریق این جریان)
                cache.delete("category_counts")
            except Exception:
                pass
            await self._auto_notify(context, 'delete_attachment', {
                'category': category, 'weapon': weapon, 'code': code, 'name': name, 'mode': mode
            })
        else:
            try:
                await safe_edit_message_text(query, t("admin.delete.error", lang))
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                else:
                    raise
        
        return await self.admin_menu_return(update, context)
    
    async def _rebuild_state_screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: int):
        """بازسازی صفحه برای هر state"""
        query = update.callback_query
        
        if state == DELETE_ATTACHMENT_MODE:
            # بازگشت به لیست modeها
            user_id = update.effective_user.id
            allowed_modes = self.role_manager.get_mode_permissions(user_id)
            lang = get_user_lang(update, context, self.db) or 'fa'
            keyboard = []
            # ترتیب: BR راست، MP چپ
            if 'br' in allowed_modes:
                keyboard.append([InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="dam_br")])
            if 'mp' in allowed_modes:
                keyboard.append([InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="dam_mp")])
            keyboard.append([InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")])
            
            try:
                await safe_edit_message_text(query, t("admin.delete.mode.prompt", lang), reply_markup=InlineKeyboardMarkup(keyboard))
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                else:
                    raise
        
        elif state == DELETE_ATTACHMENT_CATEGORY:
            # بازگشت به لیست دسته‌ها
            mode = context.user_data.get('del_att_mode', 'br')
            mode_name = GAME_MODES.get(mode, mode)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            from config.config import build_category_keyboard, is_category_enabled
            active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() if is_category_enabled(k, mode)}
            keyboard = build_category_keyboard(active_categories, "dac_")
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.weapons.choose_category", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif state == DELETE_ATTACHMENT_WEAPON:
            # بازگشت به لیست سلاح‌ها
            mode = context.user_data.get('del_att_mode', 'br')
            category = context.user_data.get('del_att_category')
            mode_name = GAME_MODES.get(mode, mode)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            if category:
                weapons = self.db.get_weapons_in_category(category)
                keyboard = self._make_weapon_keyboard(weapons, "daw_", category)
                self._add_back_cancel_buttons(keyboard, show_back=True)
                try:
                    await safe_edit_message_text(
                        query,
                        t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("weapon.choose", lang),
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        try:
                            await query.answer()
                        except Exception:
                            pass
                    else:
                        raise
        
        elif state == DELETE_ATTACHMENT_SELECT:
            # بازگشت به لیست اتچمنت‌ها
            category = context.user_data.get('del_att_category')
            weapon = context.user_data.get('del_att_weapon')
            mode = context.user_data.get('del_att_mode', 'br')
            mode_name = GAME_MODES.get(mode, mode)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            attachments = self.db.get_all_attachments(category, weapon, mode=mode)
            keyboard = []
            for att in attachments:
                keyboard.append([InlineKeyboardButton(
                    f"🗑️ {att['name']}", 
                    callback_data=f"delatt_id_{att['id']}"
                )])
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            try:
                await safe_edit_message_text(
                    query,
                    t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n" + t("admin.delete.choose_attachment", lang),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except BadRequest as e:
                if "Message is not modified" in str(e):
                    try:
                        await query.answer()
                    except Exception:
                        pass
                else:
                    raise
    
    async def _auto_notify(self, context: ContextTypes.DEFAULT_TYPE, event: str, payload: dict):
        """ارسال اعلان خودکار"""
        try:
            from managers.notification_manager import NotificationManager
            notif_manager = NotificationManager(self.db, None)
            await notif_manager.send_notification(context, event, payload)
        except Exception:
            pass
