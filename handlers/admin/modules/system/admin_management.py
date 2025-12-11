"""
ماژول مدیریت ادمین‌ها (Admin Management)
مسئول: مدیریت RBAC و نقش‌های ادمین‌ها

این ماژول شامل 14 handler برای مدیریت کامل ادمین‌ها است:
- منوی اصلی مدیریت ادمین‌ها
- افزودن ادمین جدید با نقش و نام اختصاصی
- ویرایش نقش‌های ادمین (افزودن/حذف)
- حذف ادمین
- مشاهده نقش‌ها و دسترسی‌ها
- پشتیبانی کامل از Multi-Role RBAC
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import ADMIN_MENU, ADD_ADMIN_ID, ADD_ADMIN_DISPLAY_NAME
from utils.logger import get_logger, log_admin_action
from utils.language import get_user_lang
from utils.i18n import t
from utils.telegram_safety import safe_edit_message_text

logger = get_logger('admin_mgmt', 'admin.log')


class AdminManagementHandler(BaseAdminHandler):
    """
    مدیریت ادمین‌ها و نقش‌ها
    
    Features:
    - افزودن ادمین جدید (با نقش و نام نمایشی)
    - ویرایش نقش‌های ادمین (افزودن/حذف)
    - حذف ادمین
    - مشاهده نقش‌ها و دسترسی‌ها
    - Multi-Role RBAC Support
    - Super Admin Only Access
    - Performance: Simple in-memory cache with TTL
    """
    
    def __init__(self, db):
        """مقداردهی اولیه"""
        super().__init__(db)
        self.role_manager = None
        
        # Simple in-memory cache for performance
        self._admin_list_cache = None
        self._admin_list_cache_time = 0
        self._CACHE_TTL = 300  # 5 minutes TTL (optimized from 30s)
        
        logger.info("AdminManagementHandler initialized with cache (TTL=5min)")
    
    def set_role_manager(self, role_manager):
        """تنظیم role manager"""
        self.role_manager = role_manager
    
    # ========== Cache Management ==========
    
    def _get_cached_admin_list(self):
        """
        دریافت لیست ادمین‌ها با cache
        
        Performance optimization: از query مکرر جلوگیری می‌کند
        Cache TTL: 5 minutes (optimized for better performance)
        
        Returns:
            List[Dict]: لیست ادمین‌ها
        """
        import time
        now = time.time()
        
        # اگر cache خالی یا منقضی شده
        if (self._admin_list_cache is None or 
            now - self._admin_list_cache_time > self._CACHE_TTL):
            
            # Refresh cache from database
            self._admin_list_cache = self.role_manager.get_admin_list()
            self._admin_list_cache_time = now
            
            logger.info(
                f"🔄 Admin list cache refreshed: {len(self._admin_list_cache)} admins loaded"
            )
        else:
            # استفاده از cache
            age = int(now - self._admin_list_cache_time)
            logger.debug(
                f"💾 Using cached admin list (age: {age}s, TTL: {self._CACHE_TTL}s)"
            )
        
        return self._admin_list_cache
    
    def _invalidate_admin_cache(self):
        """
        Invalidate کردن cache بعد از تغییرات
        
        این متد بعد از عملیات‌های زیر صدا زده می‌شود:
        - افزودن ادمین جدید
        - حذف ادمین
        - تغییر نقش‌ها
        """
        self._admin_list_cache = None
        self._admin_list_cache_time = 0
        logger.info("🗑️ Admin list cache invalidated")
    
    # ========== منوی اصلی ==========
    
    async def manage_admins_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """منوی مدیریت ادمین‌ها - فقط برای super admin"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # پاک کردن context برای شروع تازه
        context.user_data.pop('edit_admin_user_id', None)
        
        user_id = update.effective_user.id
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # بررسی دسترسی super admin
        if not self.role_manager.is_super_admin(user_id):
            await safe_edit_message_text(
                query,
                t("common.no_permission", lang),
                parse_mode='Markdown'
            )
            return ADMIN_MENU
        
        # دریافت لیست ادمین‌ها (با cache)
        admins = self._get_cached_admin_list()
        
        # آمار سریع
        total_admins = len(admins)
        super_admins = 0
        multi_role_admins = 0
        # شمارش نقش‌ها
        role_counts = {}
        for a in admins:
            roles = a.get('roles', []) or []
            for r in roles:
                if isinstance(r, str):
                    if r == 'super_admin':
                        super_admins += 1
                elif r.get('name') == 'super_admin':
                    super_admins += 1
            if len(roles) > 1:
                multi_role_admins += 1
            for r in roles:
                if isinstance(r, str):
                    r_name = r
                    r_disp = t(f"roles.names.{r_name}", lang) or r_name
                    r_icon = '👤'
                else:
                    r_name = r.get('name') or 'unknown'
                    r_disp = r.get('display_name') or r_name
                    r_icon = r.get('icon') or '👤'
                
                key = r_name
                if key not in role_counts:
                    role_counts[key] = {'count': 0, 'display_name': r_disp, 'icon': r_icon}
                role_counts[key]['count'] += 1
        
        # Helper: Persian digits
        def _fa(n: int) -> str:
            try:
                return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
            except Exception:
                return str(n)
        
        def _strip_emoji(s: str) -> str:
            if not s:
                return s
            ch = s[0]
            # اگر اولین کاراکتر حرف/عدد نیست، حذفش کن (اغلب ایموجی)
            if not ch.isalnum():
                return s[1:].lstrip()
            return s
        
        # هدر با آمار (RTL-friendly)
        def _n(n: int) -> str:
            return _fa(n) if (lang == 'fa') else str(n)

        text = "━━━━━━━━━━━━━━━━━━━━\n"
        text += t('admin.admin_mgmt.menu.title', lang) + "\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        # هدر و آمار تک‌زبانه
        text += t('admin.admin_mgmt.stats.header', lang) + "\n"
        text += t('admin.admin_mgmt.stats.total', lang, n=_n(total_admins) if lang == 'fa' else total_admins) + "\n"
        text += t('admin.admin_mgmt.stats.super', lang, n=_n(super_admins) if lang == 'fa' else super_admins) + "\n"
        text += t('admin.admin_mgmt.stats.multi', lang, n=_n(multi_role_admins) if lang == 'fa' else multi_role_admins) + "\n\n"
        
        if admins:
            text += t('admin.admin_mgmt.list.header', lang) + "\n"
            text += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
            
            # نمایش آمار نقش‌ها (بالای لیست)
            if role_counts:
                text += t('admin.admin_mgmt.roles.stats.header', lang) + "\n"
                # مرتب‌سازی به ترتیب بیشترین شمارش
                sorted_roles = sorted(role_counts.items(), key=lambda x: x[1]['count'], reverse=True)
                for name, info in sorted_roles:
                    if info['count'] > 0:
                        name_local_raw = t(f"roles.names.{name}", lang)
                        name_local = _strip_emoji(name_local_raw if name_local_raw and not name_local_raw.startswith('roles.names.') else info['display_name'])
                        n_local = _n(info['count']) if lang == 'fa' else str(info['count'])
                        line_local = t("admin.admin_mgmt.roles.stats.line", lang, icon=info['icon'], name=name_local, n=n_local)
                        text += line_local + "\n"
                text += "\n"
            
            for idx, admin in enumerate(admins[:8], 1):  # نمایش 8 ادمین اول
                user_id_str = admin['user_id']
                display_name = admin.get('display_name', '')
                username = admin.get('username', '')
                first_name = admin.get('first_name', '')
                
                # جمع‌آوری ایموجی‌های تمام نقش‌ها
                role_icons = []
                role_names_local = []
                roles = admin.get('roles', []) or []
                for role in roles:
                    if isinstance(role, str):
                        icon = '👤'
                        role_key = role
                        name_local_raw = t(f"roles.names.{role_key}", lang)
                        name_local = _strip_emoji(name_local_raw if name_local_raw and not name_local_raw.startswith('roles.names.') else role_key)
                    else:
                        icon = role.get('icon', '👤')
                        role_key = role.get('name') or ''
                        name_local_raw = t(f"roles.names.{role_key}", lang)
                        name_local = _strip_emoji(name_local_raw if name_local_raw and not name_local_raw.startswith('roles.names.') else (role.get('display_name') or ''))
                    
                    if icon not in role_icons:
                        role_icons.append(icon)
                    role_names_local.append(name_local)
                
                icons_str = ''.join(role_icons) if role_icons else '👤'
                roles_count = len(roles)
                
                # عنوان ردیف: شماره، آیکن، نام
                idx_fa = _fa(idx) if (lang == 'fa') else str(idx)
                if username:
                    title = f"{idx_fa}) {icons_str} **@{username}**"
                elif display_name:
                    title = f"{idx_fa}) {icons_str} **{display_name}**"
                elif first_name:
                    title = f"{idx_fa}) {icons_str} **{first_name}**"
                else:
                    title = f"{idx_fa}) {icons_str} `User_{user_id_str}`"
                
                # خط نقش‌ها: «۲ نقش: ...»
                if roles_count > 0:
                    joiner = '، ' if lang == 'fa' else ', '
                    roles_line = joiner.join(role_names_local[:4])
                    more = roles_count - 4
                    if more > 0:
                        roles_line += t("admin.admin_mgmt.list.more_roles", lang, n=_n(more) if lang == 'fa' else more)
                    line_local = t("admin.admin_mgmt.list.row.roles", lang, title=title, count=_n(roles_count) if lang == 'fa' else roles_count, roles=roles_line)
                    text += line_local + "\n"
                else:
                    line_local = t("admin.admin_mgmt.list.row.no_roles", lang, title=title, count=_n(0) if lang == 'fa' else 0)
                    text += line_local + "\n"
            
            if len(admins) > 8:
                more_n = len(admins) - 8
                text += "\n" + t('admin.admin_mgmt.more_admins', lang, n=_n(more_n) if lang == 'fa' else more_n)
        else:
            text += t('admin.admin_mgmt.none', lang)
        
        # دکمه‌های عملیات - چیدمان بهتر
        keyboard = [
            [
                InlineKeyboardButton(t("admin.admin_mgmt.buttons.add", lang), callback_data="add_new_admin"),
                InlineKeyboardButton(t("admin.admin_mgmt.buttons.view_all", lang), callback_data="view_all_admins")
            ],
            [
                InlineKeyboardButton(t("admin.admin_mgmt.buttons.edit_role", lang), callback_data="edit_admin_role"),
                InlineKeyboardButton(t("admin.admin_mgmt.buttons.roles", lang), callback_data="view_roles")
            ],
            [
                InlineKeyboardButton(t("admin.admin_mgmt.buttons.remove", lang), callback_data="remove_admin")
            ],
            [
                # بازگشت به منوی اصلی ادمین (نه همین صفحه) برای جلوگیری از خطای 'Message is not modified'
                InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="admin_back")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # ذخیره وضعیت صفحه فعلی برای جلوگیری از رندر تکراری
        context.user_data['current_view'] = 'manage_admins'
        
        try:
            await safe_edit_message_text(
                query,
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        except BadRequest as e:
            # اگر محتوای پیام تغییری نکرده باشد، به‌صورت بی‌صدا نادیده بگیر
            if 'Message is not modified' in str(e):
                return ADMIN_MENU
            raise
        
        return ADMIN_MENU
    
    # ========== افزودن ادمین جدید ==========
    
    @log_admin_action("add_admin_start")
    async def add_admin_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع افزودن ادمین جدید - انتخاب نقش"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        if not self.role_manager.is_super_admin(user_id):
            lang = get_user_lang(update, context, self.db) or 'fa'
            await safe_edit_message_text(
                query,
                t("common.no_permission", lang),
                parse_mode='Markdown'
            )
            return ADMIN_MENU
        
        # نمایش لیست نقش‌ها برای انتخاب
        roles = self.role_manager.get_all_roles()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = t("admin.admin_mgmt.add_admin.choose_role.title", lang) + "\n\n"
        text += t("admin.admin_mgmt.add_admin.choose_role.prompt", lang) + "\n\n"
        
        keyboard = []
        row = []
        for role in roles:
            callback_data = f"selrole_{role.name}"
            logger.info(f"Creating role button: {role.display_name} | callback: {callback_data}")
            row.append(InlineKeyboardButton(
                role.display_name,  # display_name خودش ایموجی دارد
                callback_data=callback_data
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")])
        
        logger.info(f"Add admin role selection menu created (grid) with {len(roles)} roles in {len(keyboard)-1} rows")
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        logger.info(f"Returning state: ADMIN_MENU (value: {ADMIN_MENU})")
        return ADMIN_MENU
    
    async def add_admin_role_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ذخیره نقش انتخاب شده و درخواست آیدی"""
        query = update.callback_query
        logger.info(f"🎯 add_admin_role_selected called! Callback data: {query.data}")
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # ذخیره نقش انتخاب شده
        role_name = query.data.replace("selrole_", "")
        context.user_data['selected_admin_role'] = role_name
        
        role = self.role_manager.get_role(role_name)
        if not role:
            await safe_edit_message_text(query, t("common.not_found", lang))
            return await self.admin_menu_return(update, context)
        
        text = t("admin.admin_mgmt.add_admin.role_selected", lang, role=role.display_name) + "\n"
        text += t("admin.admin_mgmt.add_admin.role_desc", lang, desc=role.description) + "\n\n"
        text += t("admin.admin_mgmt.add_admin.enter_id.title", lang) + "\n"
        text += t("admin.admin_mgmt.add_admin.enter_id.hint", lang)
        
        await safe_edit_message_text(query, text, parse_mode='Markdown')
        return ADD_ADMIN_ID
    
    @log_admin_action("add_admin_id_received")
    async def add_admin_id_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت User ID و درخواست نام اختصاصی"""
        try:
            lang = get_user_lang(update, context, self.db) or 'fa'
            new_admin_id = int(update.message.text.strip())
            
            # بررسی اینکه قبلاً ادمین نباشد
            if self.role_manager.is_admin(new_admin_id):
                await update.message.reply_text(t("admin.admin_mgmt.add_admin.already_admin", lang))
                context.user_data.pop('selected_admin_role', None)
                return await self.admin_menu_return(update, context)
            
            # ذخیره User ID
            context.user_data['new_admin_id'] = new_admin_id
            
            # درخواست نام اختصاصی
            await update.message.reply_text(
                t("admin.admin_mgmt.add_admin.display_name.prompt", lang),
                parse_mode='Markdown'
            )
            
            return ADD_ADMIN_DISPLAY_NAME
            
        except ValueError:
            await update.message.reply_text(t("common.invalid_id", lang))
            return ADD_ADMIN_ID
    
    @log_admin_action("add_admin_display_name_received")
    async def add_admin_display_name_received(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """دریافت نام اختصاصی و ایجاد ادمین"""
        try:
            lang = get_user_lang(update, context, self.db) or 'fa'
            display_name = update.message.text.strip()
            
            # اگر /skip باشد، نام اختصاصی خالی باشد
            if display_name == '/skip':
                display_name = None
            
            new_admin_id = context.user_data.get('new_admin_id')
            role_name = context.user_data.get('selected_admin_role', 'full_content_admin')
            
            if not new_admin_id:
                await update.message.reply_text(t("admin.admin_mgmt.errors.no_user_id", lang))
                return await self.admin_menu_return(update, context)
            
            # اضافه کردن ادمین با نقش و نام اختصاصی
            success = self.db.assign_role_to_admin(
                user_id=new_admin_id,
                role_name=role_name,
                display_name=display_name
            )
            
            if success:
                # Invalidate cache بعد از افزودن ادمین
                self._invalidate_admin_cache()
                
                role = self.role_manager.get_role(role_name)
                msg = t("admin.admin_mgmt.add_admin.success.title", lang) + "\n\n"
                if display_name:
                    msg += t("admin.admin_mgmt.add_admin.success.name_line", lang, name=display_name) + "\n"
                msg += t("admin.admin_mgmt.add_admin.success.id_line", lang, id=new_admin_id) + "\n"
                msg += t("admin.admin_mgmt.add_admin.success.role_line", lang, role=role.display_name)
                
                await update.message.reply_text(msg, parse_mode='Markdown')
            else:
                await update.message.reply_text(t("error.generic", lang))
                
        except Exception as e:
            logger.error(f"Error adding admin: {e}")
            lang = get_user_lang(update, context, self.db) or 'fa'
            await update.message.reply_text(t("error.generic", lang))
        
        # پاک کردن داده‌های موقت
        context.user_data.pop('selected_admin_role', None)
        context.user_data.pop('new_admin_id', None)
        return await self.admin_menu_return(update, context)
    
    # ========== مشاهده نقش‌ها ==========
    
    async def view_roles_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش لیست نقش‌ها و دسترسی‌ها"""
        query = update.callback_query
        await query.answer()
        
        roles = self.role_manager.get_all_roles()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        text = "━━━━━━━━━━━━━━━━━━━━\n"
        text += t('admin.admin_mgmt.roles.title', lang) + "\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        
        for idx, role in enumerate(roles, 1):
            role_name_local = t(f"roles.names.{role.name}", lang) or role.display_name
            text += f"{idx}. {role.icon} **{role_name_local}**\n"
            # توضیح نقش با fallback
            desc_local = t(f"roles.desc.{role.name}", lang)
            if not desc_local or desc_local.startswith('roles.desc.'):
                desc_local = role.description
            text += f"   📝 {desc_local}\n"
            
            # نمایش دسترسی‌ها با فرمت بهتر
            if role.permissions:
                perm_count = len(role.permissions)
                text += "   " + t('admin.admin_mgmt.roles.perms_count', lang, n=perm_count) + "\n"
                from core.security.role_manager import get_permission_display_name
                
                # نمایش 5 دسترسی اول (دو‌زبانه)
                for perm in sorted(role.permissions, key=lambda x: x.value)[:5]:
                    key = perm.value
                    perm_local = t(f"permissions.{key}", lang)
                    # اگر کلید ترجمه نبود، از نمایشگر پیش‌فرض استفاده شود
                    if not perm_local or perm_local.startswith('permissions.'):
                        perm_local = get_permission_display_name(perm)
                    text += f"      ├ {perm_local}\n"
                
                if len(role.permissions) > 5:
                    text += "      " + t('admin.admin_mgmt.roles.perms_more', lang, n=len(role.permissions) - 5) + "\n"
            else:
                text += "   " + t('admin.admin_mgmt.roles.none', lang) + "\n"
            text += "\n"
        
        keyboard = [
            [
                InlineKeyboardButton(t("admin.admin_mgmt.buttons.role_stats", lang), callback_data="role_stats"),
                InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")
            ]
        ]
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return ADMIN_MENU
    
    # ========== ویرایش نقش ادمین ==========
    
    @log_admin_action("edit_admin_role_start")
    async def edit_admin_role_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع ویرایش نقش ادمین"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not self.role_manager.is_super_admin(user_id):
            await safe_edit_message_text(
                query,
                t("common.no_permission", lang),
                parse_mode='Markdown'
            )
            return ADMIN_MENU
        
        # دریافت لیست ادمین‌ها (با cache)
        admins = self._get_cached_admin_list()
        
        if not admins:
            await safe_edit_message_text(query, t("admin.admin_mgmt.none", lang))
            return await self.admin_menu_return(update, context)
        
        text = t("admin.admin_mgmt.edit_role.title", lang) + "\n\n"
        text += t("admin.admin_mgmt.edit_role.prompt", lang) + "\n\n"
        
        logger.info(f"Building edit admin menu. Total admins: {len(admins)}")
        
        keyboard = []
        for admin in admins:
            user_id_str = str(admin['user_id'])
            display_name = admin.get('display_name', '')
            username = admin.get('username', '')
            
            logger.info(f"Processing admin: {user_id_str}, display_name: {display_name}")
            
            # جمع‌آوری ایموجی‌های تمام نقش‌ها (بدون تکرار)
            role_icons = []
            if admin.get('roles'):
                for role in admin['roles']:
                    if isinstance(role, str):
                        icon = '👤'
                    else:
                        icon = role.get('icon', '👤')
                    
                    if icon not in role_icons:
                        role_icons.append(icon)
            
            icons_str = ''.join(role_icons) if role_icons else '👤'
            
            # نمایش: فقط ایموجی + نام - اولویت: @username → display_name → first_name → ID
            if username:
                btn_text = f"{icons_str} @{username}"
            elif display_name:
                btn_text = f"{icons_str} {display_name}"
            elif admin.get('first_name'):
                btn_text = f"{icons_str} {admin.get('first_name')}"
            else:
                btn_text = f"{icons_str} {user_id_str}"
            
            callback_data = f"editadm_{user_id_str}"
            logger.info(f"✅ Button: '{btn_text}' | Callback: '{callback_data}' | Length: {len(callback_data)}")
            
            keyboard.append([InlineKeyboardButton(
                btn_text,
                callback_data=callback_data
            )])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")])
        
        logger.info(f"📋 Total buttons in keyboard: {len(keyboard)}")
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        logger.info(f"🎹 Keyboard created successfully with {len(keyboard)} rows")
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        logger.info("✅ Edit admin menu sent successfully")
        logger.info(f"🔄 Returning state: ADMIN_MENU (value: {ADMIN_MENU})")
        
        return ADMIN_MENU
    
    @log_admin_action("edit_admin_role_select")
    async def edit_admin_role_select(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """انتخاب نقش جدید برای ادمین"""
        query = update.callback_query
        logger.info(f"🎯 edit_admin_role_select called! Callback data: {query.data}")
        await query.answer()
        
        admin_user_id = int(query.data.replace("editadm_", ""))
        logger.info(f"📝 Editing admin: {admin_user_id}")
        context.user_data['edit_admin_user_id'] = admin_user_id
        
        # دریافت اطلاعات ادمین فعلی
        admin_data = self.db.get_admin(admin_user_id)
        if not admin_data:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await safe_edit_message_text(query, t("admin.admin_mgmt.errors.admin_not_found", lang))
            return await self.admin_menu_return(update, context)
        
        current_roles = admin_data.get('roles', [])
        display_name = admin_data.get('display_name', '')
        
        # اگر ادمین نقشی ندارد
        if not current_roles:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await safe_edit_message_text(query, t("admin.admin_mgmt.errors.no_roles_for_admin", lang))
            return await self.admin_menu_return(update, context)
        
        # نمایش نقش‌های فعلی
        lang = get_user_lang(update, context, self.db) or 'fa'
        current_role_lines = []
        for r in current_roles:
            if isinstance(r, str):
                role_name = r
                role_disp = t(f"roles.names.{role_name}", lang) or role_name
            else:
                role_disp = r.get('display_name') or t('common.unknown', lang)
            current_role_lines.append(f"  {role_disp}")
        
        text = t("admin.admin_mgmt.manage_roles.title", lang) + "\n\n"
        # اولویت: @username → display_name → first_name → ID
        username = admin_data.get('username', '')
        first_name = admin_data.get('first_name', '')
        
        if username:
            text += f"👤 ادمین: **@{username}** (`{admin_user_id}`)\n"
        elif display_name:
            text += f"👤 ادمین: **{display_name}** (`{admin_user_id}`)\n"
        elif first_name:
            text += f"👤 ادمین: **{first_name}** (`{admin_user_id}`)\n"
        else:
            text += f"👤 ادمین: `{admin_user_id}`\n"
        text += "\n" + t("admin.admin_mgmt.manage_roles.current_roles", lang) + "\n"
        text += '\n'.join(current_role_lines)
        text += "\n\n" + t("admin.admin_mgmt.common.what_next", lang)
        
        keyboard = [
            [InlineKeyboardButton(t("admin.admin_mgmt.buttons.add_role_new", lang), callback_data=f"addrole_{admin_user_id}")],
            [InlineKeyboardButton(t("admin.admin_mgmt.buttons.delete_role", lang), callback_data=f"delrole_{admin_user_id}")],
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")]
        ]
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return ADMIN_MENU
    
    async def add_role_to_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """افزودن نقش جدید به ادمین"""
        query = update.callback_query
        await query.answer()
        
        admin_user_id = int(query.data.replace("addrole_", ""))
        context.user_data['edit_admin_user_id'] = admin_user_id
        
        # نمایش لیست نقش‌ها
        roles = self.role_manager.get_all_roles()
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = t("admin.admin_mgmt.add_role.title", lang) + "\n\n"
        text += t("admin.admin_mgmt.add_role.prompt", lang)
        
        keyboard = []
        row = []
        for role in roles:
            row.append(InlineKeyboardButton(
                role.display_name,
                callback_data=f"newrole_{role.name}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")])
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return ADMIN_MENU
    
    async def add_role_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تایید افزودن نقش"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "admin_back":
            return await self.admin_menu_return(update, context)
        
        admin_user_id = context.user_data.get('edit_admin_user_id')
        new_role_name = query.data.replace("newrole_", "")
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not admin_user_id:
            await safe_edit_message_text(query, t("admin.admin_mgmt.errors.no_admin_id", lang))
            return await self.admin_menu_return(update, context)
        
        # افزودن نقش جدید
        success = self.db.assign_role_to_admin(admin_user_id, new_role_name)
        
        # Invalidate cache بعد از تغییر نقش
        if success:
            self._invalidate_admin_cache()
        
        if not success:
            await safe_edit_message_text(query, t("admin.admin_mgmt.add_role.error", lang))
            context.user_data.pop('edit_admin_user_id', None)
            return await self.admin_menu_return(update, context)
        
        # دریافت اطلاعات به‌روز شده
        role = self.role_manager.get_role(new_role_name)
        admin_data = self.db.get_admin(admin_user_id)
        display_name = admin_data.get('display_name', '') if admin_data else ''
        current_roles = admin_data.get('roles', []) if admin_data else []
        
        # ساخت لیست نقش‌های فعلی
        role_lines = []
        for r in current_roles:
            role_lines.append(f"  {r['display_name']}")
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        msg = t("admin.admin_mgmt.add_role.success.title", lang) + "\n\n"
        name_line = display_name if display_name else f"`{admin_user_id}`"
        msg += t("admin.admin_mgmt.labels.admin_line", lang, name=name_line, id=admin_user_id) + "\n\n"
        msg += t("admin.admin_mgmt.add_role.success.added_role", lang, role=role.display_name) + "\n\n"
        msg += t("admin.admin_mgmt.add_role.success.current_roles", lang, n=len(current_roles)) + "\n"
        msg += '\n'.join(role_lines)
        msg += "\n\n" + t("admin.admin_mgmt.common.what_next", lang)
        
        # دکمه‌های عملیات بعدی
        keyboard = [
            [InlineKeyboardButton(t("admin.admin_mgmt.buttons.add_role_more", get_user_lang(update, context, self.db) or 'fa'), callback_data=f"addrole_{admin_user_id}")],
            [InlineKeyboardButton(t("admin.admin_mgmt.buttons.delete_role", get_user_lang(update, context, self.db) or 'fa'), callback_data=f"delrole_{admin_user_id}")],
            [InlineKeyboardButton(t("admin.admin_mgmt.buttons.back_to_admins", get_user_lang(update, context, self.db) or 'fa'), callback_data="manage_admins")]
        ]
        
        await safe_edit_message_text(
            query,
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # context.user_data['edit_admin_user_id'] را نگه می‌داریم برای عملیات بعدی
        return ADMIN_MENU
    
    async def delete_role_from_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """حذف نقش از ادمین"""
        query = update.callback_query
        await query.answer()
        
        admin_user_id = int(query.data.replace("delrole_", ""))
        context.user_data['edit_admin_user_id'] = admin_user_id
        
        # دریافت نقش‌های فعلی
        admin_data = self.db.get_admin(admin_user_id)
        if not admin_data or not admin_data.get('roles'):
            lang = get_user_lang(update, context, self.db) or 'fa'
            await safe_edit_message_text(query, t("admin.admin_mgmt.errors.no_roles_for_admin", lang))
            return await self.admin_menu_return(update, context)
        
        current_roles = admin_data['roles']
        display_name = admin_data.get('display_name', '')
        
        # اگر فقط یک نقش دارد، نمی‌توان حذف کرد
        if len(current_roles) <= 1:
            role = current_roles[0]
            lang = get_user_lang(update, context, self.db) or 'fa'
            name_line = display_name if display_name else f'`{admin_user_id}`'
            msg = t("admin.admin_mgmt.delete_role.cannot_last.title", lang) + "\n\n"
            msg += t("admin.admin_mgmt.delete_role.cannot_last.body", lang, name=name_line, role=role['display_name'])
            keyboard = [
                [InlineKeyboardButton(t("admin.admin_mgmt.buttons.add_role_new", lang), callback_data=f"addrole_{admin_user_id}")],
                [InlineKeyboardButton(t("admin.admin_mgmt.buttons.remove", lang), callback_data=f"remove_confirm_{admin_user_id}")],
                [InlineKeyboardButton(t("admin.admin_mgmt.buttons.back_to_admins", lang), callback_data="manage_admins")]
            ]
            await safe_edit_message_text(
                query,
                msg,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return ADMIN_MENU
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = t("admin.admin_mgmt.del_role.title", lang) + "\n\n"
        # اولویت: @username → display_name → first_name → ID
        username = admin_data.get('username', '')
        first_name = admin_data.get('first_name', '')
        
        if username:
            name_line = f"@{username}"
        elif display_name:
            name_line = display_name
        elif first_name:
            name_line = first_name
        else:
            name_line = f"`{admin_user_id}`"
        text += t("admin.admin_mgmt.labels.admin_line", lang, name=name_line, id=admin_user_id) + "\n\n"
        text += t("admin.admin_mgmt.del_role.prompt", lang)
        
        keyboard = []
        for role in current_roles:
            keyboard.append([InlineKeyboardButton(
                role['display_name'],
                callback_data=f"delconfirm_{role['name']}"
            )])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")])
        
        await safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return ADMIN_MENU
    
    async def delete_role_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تایید حذف نقش"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "admin_back":
            return await self.admin_menu_return(update, context)
        
        admin_user_id = context.user_data.get('edit_admin_user_id')
        role_name = query.data.replace("delconfirm_", "")
        
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not admin_user_id:
            await query.edit_message_text(t("admin.admin_mgmt.errors.no_admin_id", lang))
            return await self.admin_menu_return(update, context)
        
        # جلوگیری از حذف آخرین نقش سوپرادمین سیستم
        if role_name == 'super_admin':
            all_admins = self._get_cached_admin_list()
            super_admins = [a for a in all_admins if any(r.get('name') == 'super_admin' for r in a.get('roles', []))]
            if len(super_admins) <= 1 and any(a['user_id'] == int(admin_user_id) for a in super_admins):
                await query.edit_message_text(
                    t("admin.admin_mgmt.del_role.super_last.title", lang) + "\n\n" +
                    t("admin.admin_mgmt.del_role.super_last.body", lang),
                    parse_mode='Markdown'
                )
                return ADMIN_MENU
        
        # حذف نقش
        success = self.db.remove_role_from_admin(admin_user_id, role_name)
        
        # Invalidate cache بعد از حذف نقش
        if success:
            self._invalidate_admin_cache()
        
        if not success:
            await query.edit_message_text(t("admin.admin_mgmt.del_role.error", lang))
            context.user_data.pop('edit_admin_user_id', None)
            return await self.admin_menu_return(update, context)
        
        # بررسی نقش‌های باقیمانده
        role = self.role_manager.get_role(role_name)
        admin_data = self.db.get_admin(admin_user_id)
        
        # اگر ادمین دیگر نقشی ندارد → حذف کامل
        if not admin_data or not admin_data.get('roles'):
            # حذف کامل از لیست ادمین‌ها
            self.db.remove_admin(admin_user_id)
            display = admin_data.get('display_name', '') if admin_data else ''
            name_line = display if display else f'`{admin_user_id}`'
            await query.edit_message_text(
                t("admin.admin_mgmt.remove.success.title", lang) + "\n\n" +
                t("admin.admin_mgmt.remove.success.body", lang, name=name_line, id=admin_user_id, time=self._get_current_time()),
                parse_mode='Markdown'
            )
            context.user_data.pop('edit_admin_user_id', None)
            return await self.admin_menu_return(update, context)
        
        # اگر نقش‌های دیگری دارد → نمایش نقش‌های باقیمانده
        display_name = admin_data.get('display_name', '')
        remaining_roles = admin_data['roles']
        
        # ساخت لیست نقش‌های باقیمانده
        role_lines = []
        for r in remaining_roles:
            role_lines.append(f"  {r['display_name']}")
        
        msg = t("admin.admin_mgmt.del_role.title", lang) + "\n\n"
        name_line = display_name if display_name else f'`{admin_user_id}`'
        msg += t("admin.admin_mgmt.labels.admin_line", lang, name=name_line, id=admin_user_id) + "\n\n"
        msg += t("admin.admin_mgmt.add_role.success.current_roles", lang, n=len(remaining_roles)) + "\n"
        msg += '\n'.join(role_lines)
        msg += "\n\n" + t("admin.admin_mgmt.common.what_next", lang)
        
        # دکمه‌های عملیات بعدی
        keyboard = [
            [InlineKeyboardButton(t("admin.admin_mgmt.buttons.add_role_more", get_user_lang(update, context, self.db) or 'fa'), callback_data=f"addrole_{admin_user_id}")],
            [InlineKeyboardButton(t("admin.admin_mgmt.buttons.delete_role_more", get_user_lang(update, context, self.db) or 'fa'), callback_data=f"delrole_{admin_user_id}")],
            [InlineKeyboardButton(t("admin.admin_mgmt.buttons.back_to_admins", get_user_lang(update, context, self.db) or 'fa'), callback_data="manage_admins")]
        ]
        
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        # context.user_data['edit_admin_user_id'] را نگه می‌داریم برای عملیات بعدی
        return ADMIN_MENU
    
    # ========== حذف ادمین ==========
    
    async def remove_admin_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """شروع حذف ادمین"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        if not self.role_manager.is_super_admin(user_id):
            await query.answer("❌ فقط ادمین کل می‌تواند ادمین حذف کند.", show_alert=True)
            return ADMIN_MENU
        
        # دریافت لیست ادمین‌ها (با cache)
        admins = self._get_cached_admin_list()
        
        # فیلتر کردن: حذف خود کاربر از لیست
        other_admins = [a for a in admins if a['user_id'] != user_id]
        
        if len(other_admins) == 0:
            # هیچ ادمین دیگری وجود ندارد
            text = "━━━━━━━━━━━━━━━━━━━━\n"
            text += t("admin.admin_mgmt.remove.none_exists.title", lang) + "\n"
            text += "━━━━━━━━━━━━━━━━━━━━\n\n"
            text += t("admin.admin_mgmt.remove.none_exists.body", lang)
            
            lang = get_user_lang(update, context, self.db) or 'fa'
            keyboard = [
                [InlineKeyboardButton(t("admin.admin_mgmt.buttons.add_admin_new", lang), callback_data="add_new_admin")],
                [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")]
            ]
            
            await safe_edit_message_text(
                query,
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return ADMIN_MENU
        
        keyboard = []
        for admin in other_admins:
            user_id_str = admin['user_id']
            display_name = admin.get('display_name', '')
            username = admin.get('username', '')
            
            # جمع‌آوری ایموجی‌های تمام نقش‌ها (بدون تکرار)
            role_icons = []
            if admin.get('roles'):
                for role in admin['roles']:
                    icon = role.get('icon', '👤')
                    if icon not in role_icons:
                        role_icons.append(icon)
            
            icons_str = ''.join(role_icons) if role_icons else '👤'
            
            # نمایش: فقط ایموجی + نام - اولویت: @username → display_name → first_name → ID
            if username:
                btn_text = f"❌ {icons_str} @{username}"
            elif display_name:
                btn_text = f"❌ {icons_str} {display_name}"
            elif admin.get('first_name'):
                btn_text = f"❌ {icons_str} {admin.get('first_name')}"
            else:
                btn_text = f"❌ {icons_str} {user_id_str}"
            
            keyboard.append([InlineKeyboardButton(
                btn_text,
                callback_data=f"remove_{user_id_str}"
            )])
        
        keyboard.append([InlineKeyboardButton(t("menu.buttons.back", get_user_lang(update, context, self.db) or 'fa'), callback_data="manage_admins")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.edit_message_text(
            t("admin.admin_mgmt.remove.select_admin", lang),
            reply_markup=reply_markup
        )
        
        return ADMIN_MENU
    
    async def remove_admin_confirmed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تایید و حذف ادمین - با تایید دوباره"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # اگر remove_ است، نیاز به تایید دوباره دارد
        if query.data.startswith("remove_") and not query.data.startswith("remove_confirm_"):
            admin_id = int(query.data.replace("remove_", ""))
            
            # دریافت اطلاعات ادمین برای نمایش
            admin_data = self.db.get_admin(admin_id)
            display_name = admin_data.get('display_name', f'`{admin_id}`') if admin_data else f'`{admin_id}`'
            
            # ذخیره در context برای استفاده مجدد (جلوگیری از duplicate query)
            context.user_data['temp_remove_admin_data'] = admin_data
            
            # صفحه تایید
            text = t("admin.admin_mgmt.remove.confirm.title", lang) + "\n\n" + \
                   t("admin.admin_mgmt.remove.confirm.body", lang, name=display_name, id=admin_id)
            keyboard = [
                [
                    InlineKeyboardButton(t("admin.admin_mgmt.confirm.remove.yes", lang), callback_data=f"remove_confirm_{admin_id}"),
                ],
                [
                    InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")
                ]
            ]
            
            await safe_edit_message_text(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return ADMIN_MENU
        
        # تایید نهایی - حذف واقعی
        admin_id = int(query.data.replace("remove_confirm_", ""))
        
        # بررسی اینکه نتواند خودش را حذف کند
        if admin_id == query.from_user.id:
            await query.edit_message_text(
                t("admin.admin_mgmt.remove.self.title", lang) + "\n\n" +
                t("admin.admin_mgmt.remove.self.body", lang),
                parse_mode='Markdown'
            )
        elif self.role_manager.is_admin(admin_id):
            # استفاده از داده cached از context (بهینه‌سازی - جلوگیری از duplicate query)
            admin_data = context.user_data.pop('temp_remove_admin_data', None) or self.db.get_admin(admin_id)
            display_name = admin_data.get('display_name', f'`{admin_id}`') if admin_data else f'`{admin_id}`'
            # جلوگیری از حذف تنها سوپرادمین سیستم
            if admin_data and any(r.get('name') == 'super_admin' for r in admin_data.get('roles', [])):
                all_admins = self._get_cached_admin_list()
                super_admins = [a for a in all_admins if any(r.get('name') == 'super_admin' for r in a.get('roles', []))]
                if len(super_admins) <= 1:
                    await query.edit_message_text(
                        t("admin.admin_mgmt.remove.super_last.title", lang) + "\n\n" +
                        t("admin.admin_mgmt.remove.super_last.body", lang),
                        parse_mode='Markdown'
                    )
                    return ADMIN_MENU
            
            success = self.db.remove_admin(admin_id)
            if success:
                # Invalidate cache بعد از حذف ادمین
                self._invalidate_admin_cache()
                
                await query.edit_message_text(
                    t("admin.admin_mgmt.remove.success.title", lang) + "\n\n" +
                    t("admin.admin_mgmt.remove.success.body", lang, name=display_name, id=admin_id, time=self._get_current_time()),
                    parse_mode='Markdown'
                )
            else:
                await query.edit_message_text(t("admin.admin_mgmt.remove.error", lang))
        else:
            lang = get_user_lang(update, context, self.db) or 'fa'
            await query.edit_message_text(t("admin.admin_mgmt.remove.not_admin", lang))
        
        return await self.admin_menu_return(update, context)
    
    def _get_current_time(self):
        """دریافت زمان فعلی به فرمت فارسی"""
        from datetime import datetime
        now = datetime.now()
        return now.strftime("%Y-%m-%d %H:%M")
    
    # ========== Handlers جدید برای UX بهتر ==========
    
    async def view_all_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش کامل تمام ادمین‌ها با جزئیات"""
        query = update.callback_query
        await query.answer()
        
        admins = self._get_cached_admin_list()
        lang = get_user_lang(update, context, self.db) or 'fa'

        text = "━━━━━━━━━━━━━━━━━━━━\n"
        text += t("admin.admin_mgmt.view_all.title", lang) + "\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        text += t("admin.admin_mgmt.view_all.total", lang, n=len(admins)) + "\n\n"
        
        for idx, admin in enumerate(admins, 1):
            user_id_val = admin['user_id']
            user_id_str = str(user_id_val)
            username = admin.get('username') or ''
            first_name = admin.get('first_name') or ''
            display_name = admin.get('display_name') or ''
            
            # انتخاب آیکون اصلی (اگر super_admin در نقش‌هاست از 👑 استفاده شود)
            primary_icon = '👤'
            if admin.get('roles'):
                # اگر نقش super_admin دارد
                is_super = False
                for r in admin['roles']:
                    if isinstance(r, str):
                        if r == 'super_admin':
                            is_super = True
                            break
                    elif isinstance(r, dict) and r.get('name') == 'super_admin':
                        is_super = True
                        break
                
                if is_super:
                    primary_icon = '👑'
                else:
                    # اولین آیکون نقش
                    for r in admin['roles']:
                        if isinstance(r, dict) and r.get('icon'):
                            primary_icon = r.get('icon')
                            break
            
            # خط اول: فقط نام کاربر (بدون برچسب برای سادگی i18n)
            # اولویت: @username → display_name → first_name → ID
            if username:
                text += f"{idx}. {primary_icon} @{username}\n"
            elif display_name:
                text += f"{idx}. {primary_icon} {display_name}\n"
            elif first_name:
                text += f"{idx}. {primary_icon} {first_name}\n"
            else:
                text += f"{idx}. {primary_icon} {user_id_str}\n"
            
            # خط دوم: آیدی کاربر
            text += f"   ├ 🆔 {t('common.id_label', lang)}: {user_id_str}\n\n"
        
        keyboard = [
            [InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
        return ADMIN_MENU
    
    async def role_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش آمار استفاده از نقش‌ها"""
        query = update.callback_query
        await query.answer()
        
        admins = self._get_cached_admin_list()
        roles = self.role_manager.get_all_roles()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # محاسبه آمار
        role_usage = {}
        for role in roles:
            role_usage[role.name] = {
                'display_name': role.display_name,
                'icon': role.icon,
                'count': 0
            }
        
        for admin in admins:
            for role in admin.get('roles', []):
                role_name = role.get('name')
                if role_name in role_usage:
                    role_usage[role_name]['count'] += 1
        
        # مرتب‌سازی بر اساس تعداد استفاده
        sorted_roles = sorted(role_usage.items(), key=lambda x: x[1]['count'], reverse=True)
        
        text = "━━━━━━━━━━━━━━━━━━━━\n"
        text += t("admin.admin_mgmt.role_stats.title", lang) + "\n"
        text += "━━━━━━━━━━━━━━━━━━━━\n\n"
        text += t("admin.admin_mgmt.role_stats.total_admins", lang, n=len(admins)) + "\n"
        text += t("admin.admin_mgmt.role_stats.total_roles", lang, n=len(roles)) + "\n\n"
        
        text += t("admin.admin_mgmt.role_stats.ranking_header", lang) + "\n"
        text += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"
        
        for idx, (role_name, data) in enumerate(sorted_roles, 1):
            icon = data['icon']
            display = data['display_name']
            count = data['count']
            
            # محاسبه درصد
            percentage = (count / len(admins) * 100) if len(admins) > 0 else 0
            
            # نمایش Progress Bar
            bar_length = int(percentage / 10)
            bar = "█" * bar_length + "░" * (10 - bar_length)
            
            text += t("admin.admin_mgmt.role_stats.rank.line_title", lang, i=idx, icon=icon, name=display.split()[-1]) + "\n"
            text += t("admin.admin_mgmt.role_stats.rank.bar", lang, bar=bar, percent=int(percentage)) + "\n"
            text += t("admin.admin_mgmt.role_stats.rank.count", lang, n=count) + "\n\n"
        
        keyboard = [
            [
                InlineKeyboardButton(t("admin.admin_mgmt.buttons.roles", lang), callback_data="view_roles"),
                InlineKeyboardButton(t("menu.buttons.back", lang), callback_data="manage_admins")
            ]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return ADMIN_MENU
