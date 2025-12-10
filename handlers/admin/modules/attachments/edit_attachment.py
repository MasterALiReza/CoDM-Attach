"""
ماژول ویرایش اتچمنت (REFACTORED)
مسئول: ویرایش نام، کد، و تصویر اتچمنت‌ها

ترتیب جدید: Mode → Category → Weapon → Select → Action
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from config.config import WEAPON_CATEGORIES, GAME_MODES
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import (
    EDIT_ATTACHMENT_MODE, EDIT_ATTACHMENT_CATEGORY, EDIT_ATTACHMENT_WEAPON,
    EDIT_ATTACHMENT_SELECT, EDIT_ATTACHMENT_ACTION, EDIT_ATTACHMENT_NAME,
    EDIT_ATTACHMENT_IMAGE, EDIT_ATTACHMENT_CODE
)
from utils.logger import log_admin_action
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text


class EditAttachmentHandler(BaseAdminHandler):
    """Handler برای ویرایش اتچمنت - Mode First Flow"""
    
    @log_admin_action("edit_attachment_start")
    async def edit_attachment_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع فرآیند ویرایش اتچمنت - انتخاب Mode"""
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
            mode_buttons.append(InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="eam_br"))
        if 'mp' in allowed_modes:
            mode_buttons.append(InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="eam_mp"))
        if mode_buttons:
            keyboard.append(mode_buttons)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            t("admin.edit.mode.prompt", lang),
            reply_markup=reply_markup
        )
        
        return EDIT_ATTACHMENT_MODE
    
    @log_admin_action("edit_attachment_mode_selected")
    async def edit_attachment_mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب Mode (BR/MP) برای ویرایش - سپس نمایش Categories"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست modeها
            return await self.edit_attachment_start(update, context)
        
        mode = query.data.replace("eam_", "")  # br یا mp
        
        # بررسی دسترسی به mode انتخاب شده
        user_id = update.effective_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        
        if mode not in allowed_modes:
            await query.answer(t("common.no_permission", lang), show_alert=True)
            return EDIT_ATTACHMENT_MODE
        
        # ذخیره state فعلی
        self._push_navigation(context, EDIT_ATTACHMENT_MODE, {})
        
        context.user_data['edit_att_mode'] = mode
        mode_name = GAME_MODES.get(mode, mode)
        
        # فیلتر کردن دسته‌های فعال برای mode انتخاب شده
        from config.config import build_category_keyboard, is_category_enabled
        active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() if is_category_enabled(k, mode)}
        
        if not active_categories:
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.attach.category.none_active", lang) + "\n" + t("admin.attach.category.enable_hint", lang)
            )
            return EDIT_ATTACHMENT_MODE
        
        # ساخت کیبورد 2 ستونی برای Categories فعال
        keyboard = build_category_keyboard(active_categories, "eac_")
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.weapons.choose_category", lang),
            reply_markup=reply_markup
        )
        
        return EDIT_ATTACHMENT_CATEGORY
    
    @log_admin_action("edit_attachment_category_selected")
    async def edit_attachment_category_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب دسته برای ویرایش اتچمنت - سپس نمایش Weapons"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست modeها
            context.user_data.pop('edit_att_category', None)
            return await self.edit_attachment_start(update, context)
        
        # ذخیره state فعلی
        self._push_navigation(context, EDIT_ATTACHMENT_CATEGORY, {
            'edit_att_mode': context.user_data.get('edit_att_mode')
        })
        
        category = query.data.replace("eac_", "")
        context.user_data['edit_att_category'] = category
        
        weapons = self.db.get_weapons_in_category(category)
        mode = context.user_data.get('edit_att_mode', 'br')
        mode_name = GAME_MODES.get(mode, mode)
        
        if not weapons:
            await safe_edit_message_text(
                query,
                t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("admin.weapons.none_in_category", lang)
            )
            return await self.admin_menu_return(update, context)
        
        # ساخت keyboard با تعداد ستون‌های متغیر برای سلاح‌ها
        keyboard = self._make_weapon_keyboard(weapons, "eaw_", category)
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message_text(
            query,
            t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("weapon.choose", lang),
            reply_markup=reply_markup
        )
        
        return EDIT_ATTACHMENT_WEAPON
    
    @log_admin_action("edit_attachment_weapon_selected")
    async def edit_attachment_weapon_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب سلاح برای ویرایش - مستقیم نمایش لیست Attachments"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست دسته‌ها
            context.user_data.pop('edit_att_weapon', None)
            mode = context.user_data.get('edit_att_mode', 'br')
            mode_name = GAME_MODES.get(mode, mode)
            
            from config.config import build_category_keyboard
            keyboard = build_category_keyboard(WEAPON_CATEGORIES, "eac_")
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            await safe_edit_message_text(
                query,
                f"📍 {mode_name}\n\n📂 دسته سلاح را انتخاب کنید:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return EDIT_ATTACHMENT_CATEGORY
        
        # ذخیره state فعلی
        self._push_navigation(context, EDIT_ATTACHMENT_WEAPON, {
            'edit_att_mode': context.user_data.get('edit_att_mode'),
            'edit_att_category': context.user_data.get('edit_att_category')
        })
        
        weapon = query.data.replace("eaw_", "")
        context.user_data['edit_att_weapon'] = weapon
        
        # مستقیماً به لیست اتچمنت‌ها برویم
        return await self._edit_attachment_list_menu(update, context)
    
    async def _edit_attachment_list_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ساخت و نمایش لیست اتچمنت‌ها برای انتخاب جهت ویرایش"""
        category = context.user_data['edit_att_category']
        weapon = context.user_data['edit_att_weapon']
        mode = context.user_data.get('edit_att_mode', 'br')
        mode_name = GAME_MODES.get(mode, mode)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        attachments = self.db.get_all_attachments(category, weapon, mode=mode)
        query = update.callback_query
        
        if not attachments:
            await safe_edit_message_text(
                query,
                t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n" + t("attachment.none", lang)
            )
            return await self.admin_menu_return(update, context)
        
        keyboard = []
        for att in attachments:
            # فقط نام نمایش داده میشه، ID برای callback استفاده میشه
            button_text = f"{att['name']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"eas_{att['id']}")])
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        await safe_edit_message_text(
            query,
            t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n" + t("admin.edit.choose_attachment", lang),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return EDIT_ATTACHMENT_SELECT
    
    @log_admin_action("edit_attachment_selected")
    async def edit_attachment_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب اتچمنت و شروع ویرایش (با ID)"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            return await self.handle_navigation_back(update, context)
        
        # ذخیره state فعلی
        self._push_navigation(context, EDIT_ATTACHMENT_SELECT, {
            'edit_att_mode': context.user_data.get('edit_att_mode'),
            'edit_att_category': context.user_data.get('edit_att_category'),
            'edit_att_weapon': context.user_data.get('edit_att_weapon')
        })
        
        # دریافت ID از callback
        att_id = int(query.data.replace("eas_", ""))
        
        # پیدا کردن code از روی ID
        category = context.user_data['edit_att_category']
        weapon = context.user_data['edit_att_weapon']
        mode = context.user_data.get('edit_att_mode', 'br')
        
        attachments = self.db.get_all_attachments(category, weapon, mode=mode)
        selected_att = next((att for att in attachments if att['id'] == att_id), None)
        
        if not selected_att:
            await safe_edit_message_text(query, t("attachment.not_found", lang))
            return await self.admin_menu_return(update, context)
        
        context.user_data['edit_att_code'] = selected_att['code']
        context.user_data['edit_att_id'] = att_id
        return await self.edit_attachment_action_menu(update, context)
    
    @log_admin_action("edit_attachment_action_menu")
    async def edit_attachment_action_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی عملیات ویرایش برای یک اتچمنت"""
        category = context.user_data['edit_att_category']
        weapon = context.user_data['edit_att_weapon']
        mode = context.user_data.get('edit_att_mode', 'br')
        mode_name = GAME_MODES.get(mode, mode)
        att_id = context.user_data.get('edit_att_id')
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پیدا کردن نام اتچمنت از روی ID
        attachments = self.db.get_all_attachments(category, weapon, mode=mode)
        selected_att = next((att for att in attachments if att['id'] == att_id), None)
        att_name = selected_att['name'] if selected_att else t("common.unknown", lang)
        
        text = (
            t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon) + "\n\n"
            + t("admin.edit.title", lang) + "\n\n"
            + t("admin.edit.selected_name", lang, name=att_name) + "\n\n"
            + t("admin.edit.choose_action", lang)
        )
        keyboard = [
            [InlineKeyboardButton(t("admin.edit.buttons.edit_name", lang), callback_data="eaa_name")],
            [InlineKeyboardButton(t("admin.edit.buttons.edit_code", lang), callback_data="eaa_code")],
            [InlineKeyboardButton(t("admin.edit.buttons.edit_image", lang), callback_data="eaa_image")]
        ]
        # استفاده از helper method برای consistency
        self._add_back_cancel_buttons(keyboard, show_back=True)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            try:
                await safe_edit_message_text(update.callback_query, text, reply_markup=reply_markup, parse_mode='Markdown')
            except BadRequest as e:
                # اگر محتوای پیام تغییری نکرده باشد، خطای "Message is not modified" می‌آید
                if "Message is not modified" in str(e):
                    # فقط خطا را نادیده بگیر و callback را پاسخ بده تا دکمه گیر نکند
                    try:
                        await update.callback_query.answer()
                    except Exception:
                        pass
                else:
                    raise
        else:
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        return EDIT_ATTACHMENT_ACTION
    
    @log_admin_action("edit_attachment_action_selected")
    async def edit_attachment_action_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش انتخاب عملیات ویرایش اتچمنت"""
        query = update.callback_query
        await query.answer()
        data = query.data
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # بررسی دکمه‌های خاص
        if data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if data == "nav_back":
            # بازگشت به لیست اتچمنت‌ها با استفاده از navigation stack
            return await self.handle_navigation_back(update, context)
        
        if data == "eaa_name":
            # ذخیره state فعلی قبل از رفتن به state جدید
            self._push_navigation(context, EDIT_ATTACHMENT_ACTION, {
                'edit_att_mode': context.user_data.get('edit_att_mode'),
                'edit_att_category': context.user_data.get('edit_att_category'),
                'edit_att_weapon': context.user_data.get('edit_att_weapon'),
                'edit_att_code': context.user_data.get('edit_att_code')
            })
            
            # حذف inline keyboard و reply keyboard
            keyboard = [
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")],
                [InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")]
            ]
            await safe_edit_message_text(
                query,
                t("admin.edit.name.prompt", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            # حذف reply keyboard با یک پیام جدید
            await query.message.reply_text(
                t("admin.edit.name.ask", lang),
                reply_markup=ReplyKeyboardRemove()
            )
            return EDIT_ATTACHMENT_NAME
        elif data == "eaa_image":
            # ذخیره state فعلی
            self._push_navigation(context, EDIT_ATTACHMENT_ACTION, {
                'edit_att_mode': context.user_data.get('edit_att_mode'),
                'edit_att_category': context.user_data.get('edit_att_category'),
                'edit_att_weapon': context.user_data.get('edit_att_weapon'),
                'edit_att_code': context.user_data.get('edit_att_code')
            })
            keyboard = [[InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="eaa_menu")]]
            await safe_edit_message_text(query, t("admin.edit.image.prompt", lang), reply_markup=InlineKeyboardMarkup(keyboard))
            return EDIT_ATTACHMENT_IMAGE
        elif data == "eaa_code":
            # ذخیره state فعلی
            self._push_navigation(context, EDIT_ATTACHMENT_ACTION, {
                'edit_att_mode': context.user_data.get('edit_att_mode'),
                'edit_att_category': context.user_data.get('edit_att_category'),
                'edit_att_weapon': context.user_data.get('edit_att_weapon'),
                'edit_att_code': context.user_data.get('edit_att_code')
            })
            keyboard = [
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="nav_back")],
                [InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")]
            ]
            await safe_edit_message_text(
                query,
                t("admin.edit.code.prompt", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            # حذف reply keyboard
            await query.message.reply_text(
                t("admin.edit.code.ask", lang),
                reply_markup=ReplyKeyboardRemove()
            )
            return EDIT_ATTACHMENT_CODE
        elif data == "eaa_menu":
            # خروج از مرحله ورودی تصویر: sentinel مربوط به ACTION را pop کنیم
            try:
                self._pop_navigation(context)
            except Exception:
                pass
            return await self.edit_attachment_action_menu(update, context)
        else:
            return EDIT_ATTACHMENT_ACTION
    
    @log_admin_action("edit_attachment_name_received")
    async def edit_attachment_name_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ویرایش نام اتچمنت"""
        import logging
        logger = logging.getLogger(__name__)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        try:
            new_name = update.message.text.strip()
            category = context.user_data.get('edit_att_category')
            weapon = context.user_data.get('edit_att_weapon')
            mode = context.user_data.get('edit_att_mode', 'br')
            code = context.user_data.get('edit_att_code')
            
            if not all([category, weapon, code]):
                await update.message.reply_text(t("error.generic", lang))
                return await self.admin_menu_return(update, context)
            
            # پیدا کردن نام قبلی برای اعلان
            old_name = None
            try:
                for att in self.db.get_all_attachments(category, weapon, mode=mode):
                    if att.get('code') == code:
                        old_name = att.get('name')
                        break
            except Exception as e:
                logger.error(f"Error getting old name: {e}")
            
            ok = self.db.update_attachment(category, weapon, code, new_name=new_name, new_image=None, mode=mode)
            
            if ok:
                # پاک کردن cache برای اطمینان از نمایش نام جدید
                try:
                    from core.cache.cache_manager import get_cache
                    cache = get_cache()
                    # پاک کردن تمام cache های مربوط به این سلاح
                    cache.invalidate_pattern(f"_{category}_{weapon}")
                    cache.invalidate_pattern(f"get_all_attachments")
                    cache.invalidate_pattern(f"get_weapon_attachments")
                except Exception:
                    pass  # در صورت خطا فقط نادیده می‌گیریم
                
                await update.message.reply_text(t("admin.edit.name.success", lang, new_name=new_name))
                await self._auto_notify(context, 'edit_name', {
                    'category': category, 'weapon': weapon, 'code': code,
                    'old_name': old_name or '', 'new_name': new_name, 'mode': mode
                })
            else:
                await update.message.reply_text(t("admin.edit.name.error", lang))
            # از مرحله ورودی خارج شدیم: sentinel مربوط به ACTION را از استک برداریم تا «بازگشت» فوراً به صفحه قبل برود
            try:
                self._pop_navigation(context)
            except Exception:
                pass
            
            return await self.edit_attachment_action_menu(update, context)
            
        except Exception as e:
            logger.error(f"Error in edit_attachment_name_received: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            await update.message.reply_text(t("error.generic", lang))
            return await self.admin_menu_return(update, context)
    
    @log_admin_action("edit_attachment_image_received")
    async def edit_attachment_image_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ویرایش عکس اتچمنت"""
        # بازگشت بدون تغییر
        if update.callback_query and update.callback_query.data in ("skip_edit_image", "eaa_menu"):
            await update.callback_query.answer()
            # خروج از مرحله ورودی تصویر: sentinel مربوط به ACTION را pop کنیم
            try:
                self._pop_navigation(context)
            except Exception:
                pass
            return await self.edit_attachment_action_menu(update, context)
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        # دریافت تصویر
        if update.message and update.message.photo:
            new_image = update.message.photo[-1].file_id
            category = context.user_data['edit_att_category']
            weapon = context.user_data['edit_att_weapon']
            mode = context.user_data.get('edit_att_mode', 'br')
            code = context.user_data['edit_att_code']
            ok = self.db.update_attachment(category, weapon, code, new_name=None, new_image=new_image, mode=mode)
            if ok:
                # پاک کردن cache
                try:
                    from core.cache.cache_manager import get_cache
                    cache = get_cache()
                    cache.invalidate_pattern(f"_{category}_{weapon}")
                    cache.invalidate_pattern(f"get_all_attachments")
                    cache.invalidate_pattern(f"get_weapon_attachments")
                except Exception:
                    pass
                
                await update.message.reply_text(t("admin.edit.image.success", lang))
                # اعلان خودکار
                name = None
                try:
                    for att in self.db.get_all_attachments(category, weapon, mode=mode):
                        if att.get('code') == code:
                            name = att.get('name')
                            break
                except Exception:
                    pass
                await self._auto_notify(context, 'edit_image', {
                    'category': category, 'weapon': weapon, 'code': code, 'name': name or '', 'mode': mode
                })
            else:
                await update.message.reply_text(t("admin.edit.image.error", lang))
            return await self.edit_attachment_action_menu(update, context)
        
        # اگر پیام معتبر نبود
        if update.message:
            await update.message.reply_text(t("admin.attach.image.required", lang))
            return EDIT_ATTACHMENT_IMAGE
    
    @log_admin_action("edit_attachment_code_received")
    async def edit_attachment_code_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ویرایش کد اتچمنت"""
        import logging
        logger = logging.getLogger(__name__)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        try:
            new_code = update.message.text.strip()
            category = context.user_data.get('edit_att_category')
            weapon = context.user_data.get('edit_att_weapon')
            mode = context.user_data.get('edit_att_mode', 'br')
            old_code = context.user_data.get('edit_att_code')
            
            if not all([category, weapon, old_code]):
                await update.message.reply_text(t("error.generic", lang))
                return await self.admin_menu_return(update, context)
            
            # نام را برای پیام بیابیم
            name = None
            try:
                for att in self.db.get_all_attachments(category, weapon, mode=mode):
                    if att.get('code', '').upper() == old_code.upper():
                        name = att.get('name')
                        break
            except Exception:
                pass
            
            ok = self.db.update_attachment_code(category, weapon, old_code, new_code, mode)
            if ok:
                # پاک کردن cache
                try:
                    from core.cache.cache_manager import get_cache
                    cache = get_cache()
                    cache.invalidate_pattern(f"_{category}_{weapon}")
                    cache.invalidate_pattern(f"get_all_attachments")
                    cache.invalidate_pattern(f"get_weapon_attachments")
                except Exception:
                    pass
                    
                await update.message.reply_text(t("admin.edit.code.success", lang, new_code=new_code))
                await self._auto_notify(context, 'edit_code', {
                    'category': category, 'weapon': weapon, 'name': name or '',
                    'old_code': old_code, 'new_code': new_code, 'mode': mode
                })
            else:
                await update.message.reply_text(t("admin.edit.code.error", lang))
            # خروج از مرحله ورودی کد: sentinel مربوط به ACTION را pop کنیم
            try:
                self._pop_navigation(context)
            except Exception:
                pass
            return await self.edit_attachment_action_menu(update, context)
        except Exception as e:
            logger.error(f"Error in edit_attachment_code_received: {e}")
            await update.message.reply_text(t("error.generic", lang))
            return await self.admin_menu_return(update, context)
    
    async def _rebuild_state_screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: int):
        """بازسازی صفحه برای هر state"""
        query = update.callback_query
        
        if state == EDIT_ATTACHMENT_MODE:
            # بازگشت به لیست modeها
            user_id = update.effective_user.id
            allowed_modes = self.role_manager.get_mode_permissions(user_id)
            lang = get_user_lang(update, context, self.db) or 'fa'
            keyboard = []
            # ترتیب: BR راست، MP چپ
            if 'br' in allowed_modes:
                keyboard.append([InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="eam_br")])
            if 'mp' in allowed_modes:
                keyboard.append([InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="eam_mp")])
            keyboard.append([InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")])
            
            await safe_edit_message_text(
                query,
                t("admin.edit.mode.prompt", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif state == EDIT_ATTACHMENT_CATEGORY:
            # بازگشت به لیست دسته‌ها
            mode = context.user_data.get('edit_att_mode', 'br')
            mode_name = GAME_MODES.get(mode, mode)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            from config.config import build_category_keyboard
            keyboard = build_category_keyboard(WEAPON_CATEGORIES, "eac_")
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.weapons.choose_category", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif state == EDIT_ATTACHMENT_WEAPON:
            # بازگشت به لیست سلاح‌ها
            mode = context.user_data.get('edit_att_mode', 'br')
            category = context.user_data.get('edit_att_category')
            mode_name = GAME_MODES.get(mode, mode)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            if category:
                weapons = self.db.get_weapons_in_category(category)
                keyboard = self._make_weapon_keyboard(weapons, "eaw_", category)
                self._add_back_cancel_buttons(keyboard, show_back=True)
                await safe_edit_message_text(
                    query,
                    t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("weapon.choose", lang),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
        
        elif state == EDIT_ATTACHMENT_SELECT:
            # بازگشت به لیست اتچمنت‌ها
            await self._edit_attachment_list_menu(update, context)
        
        elif state == EDIT_ATTACHMENT_ACTION:
            # بازگشت به منوی عملیات
            await self.edit_attachment_action_menu(update, context)
    
    async def _auto_notify(self, context: ContextTypes.DEFAULT_TYPE, event: str, payload: dict):
        """ارسال اعلان خودکار"""
        try:
            from managers.notification_manager import NotificationManager
            notif_manager = NotificationManager(self.db, None)
            await notif_manager.send_notification(context, event, payload)
        except Exception:
            pass
