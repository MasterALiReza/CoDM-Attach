"""
ماژول افزودن اتچمنت (REFACTORED)
مسئول: افزودن اتچمنت جدید، ایجاد سلاح inline، تنظیم Top/Season

ترتیب جدید: Mode → Category → Weapon → Code/Name/Image → Top/Season
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from config.config import WEAPON_CATEGORIES, GAME_MODES
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import (
    ADD_ATTACHMENT_MODE, ADD_ATTACHMENT_CATEGORY, ADD_ATTACHMENT_WEAPON,
    ADD_ATTACHMENT_CODE, ADD_ATTACHMENT_NAME, ADD_ATTACHMENT_IMAGE,
    ADD_ATTACHMENT_TOP, ADD_ATTACHMENT_SEASON, ADD_WEAPON_NAME
)
from utils.logger import log_admin_action, get_logger
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text
from utils.validators_enhanced import AttachmentValidator, TextValidator

logger = get_logger('admin.add_attachment', 'admin.log')


class AddAttachmentHandler(BaseAdminHandler):
    """Handler برای افزودن اتچمنت - Mode First Flow"""
    
    @log_admin_action("add_attachment_start")
    async def add_attachment_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع فرآیند افزودن اتچمنت - انتخاب Mode"""
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
            mode_buttons.append(InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="aam_br"))
        if 'mp' in allowed_modes:
            mode_buttons.append(InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="aam_mp"))
        if mode_buttons:
            keyboard.append(mode_buttons)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await safe_edit_message_text(query, t("admin.attach.mode.prompt", lang), reply_markup=reply_markup)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        
        return ADD_ATTACHMENT_MODE
    
    @log_admin_action("add_attachment_mode_selected")
    async def add_attachment_mode_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب Mode (BR/MP) برای اتچمنت - سپس نمایش Categories"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست modeها
            return await self.add_attachment_start(update, context)
        
        mode = query.data.replace("aam_", "")  # br یا mp
        
        # بررسی دسترسی به mode انتخاب شده
        user_id = update.effective_user.id
        allowed_modes = self.role_manager.get_mode_permissions(user_id)
        
        if mode not in allowed_modes:
            await query.answer(t("common.no_permission", lang), show_alert=True)
            return ADD_ATTACHMENT_MODE
        
        # ذخیره state فعلی
        self._push_navigation(context, ADD_ATTACHMENT_MODE, {})
        
        context.user_data['add_att_mode'] = mode
        mode_name = GAME_MODES.get(mode, mode)
        
        # فیلتر کردن دسته‌های فعال برای mode انتخاب شده
        from config.config import build_category_keyboard, is_category_enabled
        active_categories = {k: v for k, v in WEAPON_CATEGORIES.items() if is_category_enabled(k, mode)}
        
        if not active_categories:
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.attach.category.none_active", lang) + "\n" + t("admin.attach.category.enable_hint", lang)
            )
            return ADD_ATTACHMENT_MODE
        
        # ساخت کیبورد 2 ستونی برای Categories فعال
        keyboard = build_category_keyboard(active_categories, "aac_")
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
        
        return ADD_ATTACHMENT_CATEGORY
    
    @log_admin_action("add_attachment_category_selected")
    async def add_attachment_category_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب دسته برای افزودن اتچمنت - سپس نمایش Weapons"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست modeها
            context.user_data.pop('add_att_category', None)
            return await self.add_attachment_start(update, context)
        
        # ذخیره state فعلی
        self._push_navigation(context, ADD_ATTACHMENT_CATEGORY, {
            'add_att_mode': context.user_data.get('add_att_mode')
        })
        
        category = query.data.replace("aac_", "")
        context.user_data['add_att_category'] = category
        
        # 🔍 DEBUG: بررسی category و callback
        logger.info(f"🔍 Category selected: callback_data='{query.data}', extracted_category='{category}'")
        
        weapons = self.db.get_weapons_in_category(category)
        
        # 🔍 DEBUG: بررسی weapons یافت شده
        logger.info(f"🔍 Weapons found for '{category}': {len(weapons)} weapons")
        if weapons:
            logger.info(f"🔍 Sample weapons: {', '.join(weapons[:5])}")
        
        mode = context.user_data.get('add_att_mode', 'br')
        mode_name = GAME_MODES.get(mode, mode)
        
        # اگر هیچ سلاحی در این دسته وجود ندارد، از ادمین نام سلاح جدید را بگیر
        if not weapons:
            await safe_edit_message_text(
                query,
                t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("admin.attach.weapon.none", lang) + "\n" + t("admin.attach.weapon.prompt_new_name", lang)
            )
            return ADD_WEAPON_NAME
        
        # ساخت keyboard با تعداد ستون‌های متغیر برای سلاح‌ها
        keyboard = [[InlineKeyboardButton(t("admin.attach.buttons.add_weapon", lang), callback_data="aaw_new")]]
        keyboard.extend(self._make_weapon_keyboard(weapons, "aaw_", category))
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
        
        return ADD_ATTACHMENT_WEAPON
    
    @log_admin_action("add_attachment_weapon_selected")
    async def add_attachment_weapon_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب سلاح برای افزودن اتچمنت - سپس درخواست Code"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        if query.data == "admin_cancel":
            return await self.admin_menu_return(update, context)
        
        if query.data == "nav_back":
            # بازگشت به لیست دسته‌ها
            context.user_data.pop('add_att_weapon', None)
            mode = context.user_data.get('add_att_mode', 'br')
            mode_name = GAME_MODES.get(mode, mode)
            
            from config.config import build_category_keyboard
            keyboard = build_category_keyboard(WEAPON_CATEGORIES, "aac_")
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            await safe_edit_message_text(
                query,
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.weapons.choose_category", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ADD_ATTACHMENT_CATEGORY
        
        # اگر گزینه افزودن سلاح جدید انتخاب شد، نام سلاح را از کاربر بگیر
        if query.data == "aaw_new":
            mode = context.user_data.get('add_att_mode', 'br')
            category = context.user_data.get('add_att_category')
            mode_name = GAME_MODES.get(mode, mode)
            
            await safe_edit_message_text(
                query,
                t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("admin.attach.weapon.prompt_new_name", lang)
            )
            return ADD_WEAPON_NAME
        
        # ذخیره state فعلی
        self._push_navigation(context, ADD_ATTACHMENT_WEAPON, {
            'add_att_mode': context.user_data.get('add_att_mode'),
            'add_att_category': context.user_data.get('add_att_category')
        })
        
        weapon = query.data.replace("aaw_", "")
        context.user_data['add_att_weapon'] = weapon
        
        mode = context.user_data.get('add_att_mode', 'br')
        category = context.user_data.get('add_att_category')
        mode_name = GAME_MODES.get(mode, mode)
        
        try:
            await safe_edit_message_text(
                query,
                t("admin.attach.code.header", lang) + "\n" + t("admin.attach.code.example", lang) + "\n\n" + t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon)
            )
        except BadRequest as e:
            if "Message is not modified" in str(e):
                try:
                    await query.answer()
                except Exception:
                    pass
            else:
                raise
        # حذف ReplyKeyboard کاربر تا ورودی متن به درستی در همین مکالمه پردازش شود
        try:
            await query.message.reply_text(t("admin.attach.code.ask", lang), reply_markup=ReplyKeyboardRemove())
        except Exception:
            pass
        
        return ADD_ATTACHMENT_CODE
    
    @log_admin_action("add_attachment_new_weapon_name_received")
    async def add_attachment_new_weapon_name_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        دریافت نام سلاح جدید در فرآیند افزودن اتچمنت
        
        Uses: TextValidator for weapon name validation
        """
        weapon_name = update.message.text.strip()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # ✅ استفاده از validator مشترک
        result = TextValidator.validate_length(
            weapon_name,
            max_length=50,
            min_length=2,
            field_name="weapon_name"
        )
        
        if not result.is_valid:
            error_msg = t(result.error_key, lang, **(result.error_details or {}))
            await update.message.reply_text(
                error_msg + "\n" + t("admin.attach.weapon.prompt_new_name", lang)
            )
            return ADD_WEAPON_NAME
        
        context.user_data['add_att_weapon'] = weapon_name
        
        mode = context.user_data.get('add_att_mode', 'br')
        category = context.user_data.get('add_att_category')
        mode_name = GAME_MODES.get(mode, mode)
        
        await update.message.reply_text(
            t("admin.attach.weapon.saved", lang, weapon=weapon_name) + "\n\n" + 
            t("admin.attach.code.header", lang) + "\n" + 
            t("admin.attach.code.example", lang) + "\n\n" + 
            t("admin.weapons.path_weapon", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category), weapon=weapon_name),
            reply_markup=ReplyKeyboardRemove()
        )
        return ADD_ATTACHMENT_CODE
    
    @log_admin_action("add_attachment_code_received")
    async def add_attachment_code_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        دریافت کد اتچمنت
        
        Uses: AttachmentValidator.validate_code() for robust validation
        """
        code = update.message.text.strip().upper()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # ✅ استفاده از validator مشترک با i18n
        result = AttachmentValidator.validate_code(code)
        
        if not result.is_valid:
            error_msg = t(result.error_key, lang, **(result.error_details or {}))
            await update.message.reply_text(
                error_msg + "\n" + 
                t("admin.attach.code.header", lang) + "\n" + 
                t("admin.attach.code.example", lang)
            )
            return ADD_ATTACHMENT_CODE
        
        context.user_data['add_att_code'] = code
        
        await update.message.reply_text(
            t("admin.attach.code.saved", lang, code=code) + "\n\n" + 
            t("admin.attach.name.prompt", lang) + "\n" + 
            t("admin.attach.name.example", lang),
            parse_mode='Markdown',
            reply_markup=ReplyKeyboardRemove()
        )
        
        return ADD_ATTACHMENT_NAME
    
    @log_admin_action("add_attachment_name_received")
    async def add_attachment_name_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت نام اتچمنت"""
        name = update.message.text.strip()
        context.user_data['add_att_name'] = name
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # دکمه برای رد کردن ارسال عکس
        skip_markup = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("admin.attach.buttons.skip_image", lang), callback_data="skip_image")
        ]])
        await update.message.reply_text(
            t("admin.attach.image.prompt", lang),
            reply_markup=skip_markup
        )
        
        return ADD_ATTACHMENT_IMAGE
    
    @log_admin_action("add_attachment_image_received")
    async def add_attachment_image_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت عکس اتچمنت"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پشتیبانی از رد کردن ارسال عکس با دکمه
        if update.callback_query:
            query = update.callback_query
            await query.answer()
            if query.data == "skip_image":
                context.user_data['add_att_image'] = ""
                keyboard = self._create_confirmation_keyboard(
                    confirm_callback="att_top_yes",
                    cancel_callback="att_top_no",
                    confirm_text=t("admin.attach.buttons.top.yes", lang),
                    cancel_text=t("admin.attach.buttons.top.no", lang),
                    show_back=False
                )
                try:
                    await safe_edit_message_text(query, t("admin.attach.top.question", lang), reply_markup=InlineKeyboardMarkup(keyboard))
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        try:
                            await query.answer()
                        except Exception:
                            pass
                    else:
                        raise
                return ADD_ATTACHMENT_TOP
        
        if not update.message or not update.message.photo:
            if update.message:
                await update.message.reply_text(t("admin.attach.image.required", lang))
            return ADD_ATTACHMENT_IMAGE
        
        image = update.message.photo[-1].file_id
        context.user_data['add_att_image'] = image
        
        keyboard = self._create_confirmation_keyboard(
            confirm_callback="att_top_yes",
            cancel_callback="att_top_no",
            confirm_text=t("admin.attach.buttons.top.yes", lang),
            cancel_text=t("admin.attach.buttons.top.no", lang),
            show_back=False
        )
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(t("admin.attach.top.question", lang), reply_markup=reply_markup)
        return ADD_ATTACHMENT_TOP
    
    @log_admin_action("add_attachment_top_selected")
    async def add_attachment_top_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب وضعیت «برتر سلاح» و انتقال به سوال برتر فصل"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        is_top = query.data == "att_top_yes"
        context.user_data['add_att_is_top'] = is_top
        
        # مرحله دوم: پرسش درباره برتر فصل
        keyboard = self._create_confirmation_keyboard(
            confirm_callback="att_season_yes",
            cancel_callback="att_season_no",
            confirm_text=t("admin.attach.buttons.season.yes", lang),
            cancel_text=t("admin.attach.buttons.season.no", lang),
            show_back=False
        )
        await safe_edit_message_text(query, t("admin.attach.season.question", lang), reply_markup=InlineKeyboardMarkup(keyboard))
        return ADD_ATTACHMENT_SEASON
    
    @log_admin_action("add_attachment_season_selected")
    async def add_attachment_season_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب وضعیت «برتر فصل» و ذخیره نهایی اتچمنت"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        is_season_top = (query.data == "att_season_yes")
        is_top = bool(context.user_data.get('add_att_is_top', False))
        
        mode = context.user_data.get('add_att_mode', 'br')
        category = context.user_data['add_att_category']
        weapon = context.user_data['add_att_weapon']
        code = context.user_data['add_att_code']
        name = context.user_data['add_att_name']
        image = context.user_data['add_att_image']
        
        mode_name = GAME_MODES.get(mode, mode)
        
        if self.db.add_attachment(category, weapon, code, name, image, is_top, is_season_top, mode=mode):
            # پاک کردن cache برای نمایش فوری اتچمنت جدید
            try:
                from core.cache.cache_manager import invalidate_attachment_caches
                invalidate_attachment_caches(category, weapon)
            except Exception:
                pass
                
            status_lines = []
            status_lines.append(t("admin.attach.status.top", lang) if is_top else t("admin.attach.status.normal", lang))
            if is_season_top:
                status_lines.append(t("admin.attach.status.season_top", lang))
            
            await safe_edit_message_text(
                query,
                t("admin.attach.success.title", lang, name=name) + "\n\n"
                + t("admin.attach.summary.header", lang) + "\n"
                + t("attachment.code", lang) + f": {code}\n"
                + t("weapon.label", lang) + f": {weapon}\n"
                + t("mode.label", lang) + f": {mode_name}\n"
                + t("admin.attach.summary.status_label", lang) + f": {' | '.join(status_lines)}"
            )
            
            # اعلان خودکار
            await self._auto_notify(context, 'add_attachment', {
                'category': category, 'weapon': weapon, 'code': code, 'name': name, 'mode': mode
            })
            if is_top:
                await self._auto_notify(context, 'top_added', {
                    'category': category, 'weapon': weapon, 'code': code, 'name': name, 'mode': mode
                })
        else:
            await safe_edit_message_text(query, t("admin.attach.error.save", lang))
        
        # پاکسازی user_data
        context.user_data.pop('add_att_is_top', None)
        return await self.admin_menu_return(update, context)

    # ========= Ignore stray text during callback-only steps =========
    @log_admin_action("add_attachment_top_ignore_text")
    async def add_attachment_top_ignore_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """جلوگیری از تداخل هندلرهای کاربری هنگام مرحله انتخاب Top"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        await update.message.reply_text(t("common.use_buttons", lang))
        return ADD_ATTACHMENT_TOP

    @log_admin_action("add_attachment_season_ignore_text")
    async def add_attachment_season_ignore_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """جلوگیری از تداخل هندلرهای کاربری هنگام مرحله انتخاب برتر فصل"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        await update.message.reply_text(t("common.use_buttons", lang))
        return ADD_ATTACHMENT_SEASON
    
    async def _rebuild_state_screen(self, update: Update, context: ContextTypes.DEFAULT_TYPE, state: int):
        """بازسازی صفحه برای هر state"""
        query = update.callback_query
        
        if state == ADD_ATTACHMENT_MODE:
            # بازگشت به لیست modeها
            user_id = update.effective_user.id
            allowed_modes = self.role_manager.get_mode_permissions(user_id)
            lang = get_user_lang(update, context, self.db) or 'fa'
            keyboard = []
            # ترتیب: BR راست، MP چپ
            if 'br' in allowed_modes:
                keyboard.append([InlineKeyboardButton(f"{t('mode.br', lang)} ({t('mode.br_short', lang)})", callback_data="aam_br")])
            if 'mp' in allowed_modes:
                keyboard.append([InlineKeyboardButton(f"{t('mode.mp', lang)} ({t('mode.mp_short', lang)})", callback_data="aam_mp")])
            keyboard.append([InlineKeyboardButton(t("menu.buttons.cancel", lang), callback_data="admin_cancel")])
            
            await safe_edit_message_text(
                query,
                t("admin.attach.mode.prompt", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif state == ADD_ATTACHMENT_CATEGORY:
            # بازگشت به لیست دسته‌ها
            mode = context.user_data.get('add_att_mode', 'br')
            mode_name = GAME_MODES.get(mode, mode)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            from config.config import build_category_keyboard
            keyboard = build_category_keyboard(WEAPON_CATEGORIES, "aac_")
            self._add_back_cancel_buttons(keyboard, show_back=True)
            
            await query.edit_message_text(
                t("admin.weapons.header.mode", lang, mode=mode_name) + "\n\n" + t("admin.weapons.choose_category", lang),
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        elif state == ADD_ATTACHMENT_WEAPON:
            # بازگشت به لیست سلاح‌ها
            mode = context.user_data.get('add_att_mode', 'br')
            category = context.user_data.get('add_att_category')
            mode_name = GAME_MODES.get(mode, mode)
            lang = get_user_lang(update, context, self.db) or 'fa'
            
            if category:
                weapons = self.db.get_weapons_in_category(category)
                keyboard = [[InlineKeyboardButton(t("admin.attach.buttons.add_weapon", lang), callback_data="aaw_new")]]
                keyboard.extend(self._make_weapon_keyboard(weapons, "aaw_", category))
                self._add_back_cancel_buttons(keyboard, show_back=True)
                await safe_edit_message_text(
                    query,
                    t("admin.weapons.path", lang, mode=mode_name, category=WEAPON_CATEGORIES.get(category)) + "\n\n" + t("weapon.choose", lang),
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
    
    async def _auto_notify(self, context: ContextTypes.DEFAULT_TYPE, event: str, payload: dict):
        """ارسال اعلان خودکار"""
        try:
            from managers.notification_manager import NotificationManager
            notif_manager = NotificationManager(self.db, None)
            await notif_manager.send_notification(context, event, payload)
        except Exception:
            pass
