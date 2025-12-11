"""
سیستم مدیریت نقش‌ها و دسترسی‌ها (RBAC - Role-Based Access Control)
این سیستم امکان تعریف نقش‌های مختلف برای ادمین‌ها و محدودسازی دسترسی آن‌ها را فراهم می‌کند.
"""

from typing import List, Dict, Optional, Set
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
import logging
from core.cache.cache_manager import get_cache

logger = logging.getLogger(__name__)


# Singleton instance
_role_manager_instance = None


def get_role_manager(db=None):
    """دریافت singleton instance از RoleManager"""
    global _role_manager_instance
    if _role_manager_instance is None and db is not None:
        _role_manager_instance = RoleManager(db)
    return _role_manager_instance


class Permission(str, Enum):
    """دسترسی‌های مختلف سیستم"""
    # مدیریت محتوا
    MANAGE_ATTACHMENTS_BR = "manage_attachments_br"
    MANAGE_ATTACHMENTS_MP = "manage_attachments_mp"
    MANAGE_SUGGESTED_ATTACHMENTS = "manage_suggested_attachments"  # مدیریت اتچمنت‌های پیشنهادی
    MANAGE_USER_ATTACHMENTS = "manage_user_attachments"  # مدیریت اتچمنت‌های کاربران
    
    # مدیریت راهنماها (تنظیمات بازی)
    MANAGE_GUIDES_BR = "manage_guides_br"
    MANAGE_GUIDES_MP = "manage_guides_mp"
    
    # مدیریت محتوای متنی
    MANAGE_TEXTS = "manage_texts"  # مدیریت متن‌های سیستم
    # مدیریت CMS
    MANAGE_CMS = "manage_cms"
    
    # مدیریت سیستم
    MANAGE_CHANNELS = "manage_channels"
    MANAGE_ADMINS = "manage_admins"
    MANAGE_CATEGORIES = "manage_categories"
    
    # سایر دسترسی‌های عمومی (موجود در دیتابیس)
    MANAGE_USERS = "manage_users"
    MANAGE_ATTACHMENTS = "manage_attachments"
    VIEW_ANALYTICS = "view_analytics"
    MODERATE_CONTENT = "moderate_content"
    MANAGE_REPORTS = "manage_reports"
    MANAGE_TICKETS = "manage_tickets"
    MANAGE_FAQS = "manage_faqs"
    ALL = "all"
    MANAGE_SETTINGS = "manage_settings"
    
    # ارتباطات
    SEND_NOTIFICATIONS = "send_notifications"
    MANAGE_NOTIFICATION_SETTINGS = "manage_notification_settings"
    MANAGE_SCHEDULED_NOTIFICATIONS = "manage_scheduled_notifications"
    
    # پشتیبانی و تیکتینگ
    MANAGE_TICKETS = "manage_tickets"
    MANAGE_FAQS = "manage_faqs"
    VIEW_FEEDBACK = "view_feedback"
    
    # داده و گزارش
    VIEW_ANALYTICS = "view_analytics"
    BACKUP_DATA = "backup_data"
    IMPORT_EXPORT = "import_export"
    
    # Data Health Management
    VIEW_HEALTH_REPORTS = "view_health_reports"
    RUN_HEALTH_CHECKS = "run_health_checks"
    FIX_DATA_ISSUES = "fix_data_issues"


@dataclass
class Role:
    """تعریف یک نقش با دسترسی‌های مشخص"""
    name: str
    display_name: str  # نام فارسی برای نمایش
    description: str
    permissions: Set[Permission] = field(default_factory=set)
    icon: str = "👤"  # آیکون نقش
    
    def has_permission(self, permission: Permission) -> bool:
        """بررسی وجود دسترسی"""
        return permission in self.permissions
    
    def add_permission(self, permission: Permission):
        """اضافه کردن دسترسی"""
        self.permissions.add(permission)
    
    def remove_permission(self, permission: Permission):
        """حذف دسترسی"""
        self.permissions.discard(permission)


class RoleManager:
    """مدیریت نقش‌ها و دسترسی‌ها"""
    
    _instance = None
    _initialized = False
    
    # تعریف نقش‌های پیش‌فرض
    PREDEFINED_ROLES = {
        "super_admin": Role(
            name="super_admin",
            display_name="👑 ادمین کل",
            description="دسترسی کامل به تمام بخش‌ها",
            icon="👑",
            permissions={
                Permission.MANAGE_ATTACHMENTS_BR,
                Permission.MANAGE_ATTACHMENTS_MP,
                Permission.MANAGE_SUGGESTED_ATTACHMENTS,
                Permission.MANAGE_USER_ATTACHMENTS,
                Permission.MANAGE_GUIDES_BR,
                Permission.MANAGE_GUIDES_MP,
                Permission.MANAGE_TEXTS,
                Permission.MANAGE_CMS,
                Permission.MANAGE_CHANNELS,
                Permission.MANAGE_ADMINS,
                Permission.MANAGE_CATEGORIES,
                Permission.MANAGE_SETTINGS,
                Permission.SEND_NOTIFICATIONS,
                Permission.MANAGE_NOTIFICATION_SETTINGS,
                Permission.MANAGE_SCHEDULED_NOTIFICATIONS,
                Permission.MANAGE_TICKETS,
                Permission.MANAGE_FAQS,
                Permission.VIEW_FEEDBACK,
                Permission.VIEW_ANALYTICS,
                Permission.BACKUP_DATA,
                Permission.IMPORT_EXPORT,
                Permission.VIEW_HEALTH_REPORTS,
                Permission.RUN_HEALTH_CHECKS,
                Permission.FIX_DATA_ISSUES,
            }
        ),
        "br_admin": Role(
            name="br_admin",
            display_name="🪂 ادمین بتل رویال",
            description="مدیریت اتچمنت‌ها، پیشنهادی‌ها و تنظیمات بتل رویال",
            icon="🪂",
            permissions={
                Permission.MANAGE_ATTACHMENTS_BR,
                Permission.MANAGE_SUGGESTED_ATTACHMENTS,
                Permission.MANAGE_GUIDES_BR,
                Permission.VIEW_ANALYTICS,
            }
        ),
        "mp_admin": Role(
            name="mp_admin",
            display_name="🎮 ادمین مولتی پلیر",
            description="مدیریت اتچمنت‌ها، پیشنهادی‌ها و تنظیمات مولتی پلیر",
            icon="🎮",
            permissions={
                Permission.MANAGE_ATTACHMENTS_MP,
                Permission.MANAGE_SUGGESTED_ATTACHMENTS,
                Permission.MANAGE_GUIDES_MP,
                Permission.VIEW_ANALYTICS,
            }
        ),
        "full_content_admin": Role(
            name="full_content_admin",
            display_name="📎 ادمین محتوا",
            description="مدیریت کامل محتوا: اتچمنت‌ها، پیشنهادی‌ها، راهنماها، متن‌ها و بکاپ",
            icon="📎",
            permissions={
                Permission.MANAGE_ATTACHMENTS_BR,
                Permission.MANAGE_ATTACHMENTS_MP,
                Permission.MANAGE_SUGGESTED_ATTACHMENTS,
                Permission.MANAGE_USER_ATTACHMENTS,
                Permission.MANAGE_GUIDES_BR,
                Permission.MANAGE_GUIDES_MP,
                Permission.MANAGE_TEXTS,
                Permission.MANAGE_CMS,
                Permission.MANAGE_CATEGORIES,
                Permission.SEND_NOTIFICATIONS,
                Permission.MANAGE_SCHEDULED_NOTIFICATIONS,
                Permission.BACKUP_DATA,
                Permission.VIEW_ANALYTICS,
            }
        ),
        "ua_moderator": Role(
            name="ua_moderator",
            display_name="🎮 ادمین اتچمنت کاربران",
            description="مدیریت سیستم اتچمنت‌های کاربران (بررسی/تایید/رد/تنظیمات)",
            icon="🎮",
            permissions={
                Permission.MANAGE_USER_ATTACHMENTS,
                Permission.VIEW_ANALYTICS,
            }
        ),
        "support_admin": Role(
            name="support_admin",
            display_name="📞 ادمین پشتیبانی",
            description="مدیریت تیکت‌ها، FAQ و بازخوردها",
            icon="📞",
            permissions={
                Permission.MANAGE_TICKETS,
                Permission.MANAGE_FAQS,
                Permission.VIEW_FEEDBACK,
            }
        ),
    }
    
    def __init__(self, db):
        """
        Args:
            db: شیء DatabaseSQL برای مدیریت دیتابیس
        """
        self.db = db
        
        # Simple cache for role definitions (static data - rarely changes)
        self._roles_cache = None
        # Shared in-process cache (thread-safe) for hot paths
        self.cache = get_cache()
        
        # فقط یکبار roles رو initialize می‌کنیم
        if not RoleManager._initialized:
            self._init_predefined_roles()
            RoleManager._initialized = True
            logger.info("✅ RoleManager initialized (first time only)")
    
    def _init_predefined_roles(self):
        """ایجاد نقش‌های پیش‌فرض در دیتابیس (فقط یکبار)"""
        for role_name, role in self.PREDEFINED_ROLES.items():
            self.db.create_role_if_not_exists(
                role_name=role.name,
                display_name=role.display_name,
                description=role.description,
                icon=role.icon,
                permissions=list(role.permissions)
            )
    
    def get_role(self, role_name: str) -> Optional[Role]:
        """دریافت اطلاعات یک نقش"""
        # Prefer in-memory cached role definitions to avoid extra queries
        if self._roles_cache is None:
            # Warm the cache once
            _ = self.get_all_roles()
        # Try to resolve from cached roles
        if self._roles_cache:
            for r in self._roles_cache:
                if r.name == role_name:
                    return r
        # Fallback to DB (rare path)
        role_data = self.db.get_role(role_name)
        if not role_data:
            return None
        return Role(
            name=role_data['name'],
            display_name=role_data['display_name'],
            description=role_data['description'],
            icon=role_data.get('icon', '👤'),
            permissions=set(Permission(p) for p in role_data['permissions'])
        )
    
    def get_all_roles(self) -> List[Role]:
        """
        دریافت تمام نقش‌ها (با cache)
        
        Performance: Role definitions تقریباً هیچوقت تغییر نمی‌کنند،
        پس یکبار load می‌کنیم و cache می‌کنیم.
        """
        if self._roles_cache is None:
            # Load from database first time
            roles_data = self.db.get_all_roles()
            self._roles_cache = [
                Role(
                    name=r['name'],
                    display_name=r['display_name'],
                    description=r['description'],
                    icon=r.get('icon', '👤'),
                    permissions=set(Permission(p) for p in r['permissions'])
                )
                for r in roles_data
            ]
            logger.info(f"📦 Loaded {len(self._roles_cache)} role definitions into cache")
        
        return self._roles_cache
    
    def assign_role(self, user_id: int, role_name: str) -> bool:
        """اختصاص نقش به کاربر"""
        role = self.get_role(role_name)
        if not role:
            logger.error(f"نقش {role_name} یافت نشد")
            return False
        
        return self.db.assign_role_to_admin(user_id, role_name)
    
    def remove_role(self, user_id: int) -> bool:
        """حذف نقش کاربر"""
        return self.db.remove_admin(user_id)
    
    def get_user_role(self, user_id: int) -> Optional[Role]:
        """دریافت اولین نقش کاربر (backward compatibility)"""
        admin_data = self.db.get_admin(user_id)
        if not admin_data:
            return None
        
        return self.get_role(admin_data['role_name'])
    
    def get_user_roles(self, user_id: int) -> List[Role]:
        """دریافت تمام نقش‌های کاربر (با cache کوتاه‌مدت)"""
        cache_key = f"user_roles_{user_id}"
        cached_roles = self.cache.get(cache_key)
        if cached_roles is not None:
            return cached_roles

        # PostgreSQL multi-role schema stores roles in admin_roles (user_id <-> role_id)
        try:
            role_names = self.db.get_admin_roles(user_id)
        except Exception as e:
            logger.error(f"Error loading roles for user {user_id}: {e}")
            role_names = []

        if not role_names:
            roles: List[Role] = []
            self.cache.set(cache_key, roles, ttl=120)
            return roles

        # Resolve roles using cached definitions
        roles: List[Role] = []
        for role_name in role_names:
            role = self.get_role(role_name)
            if role:
                roles.append(role)
        # Cache for 2 minutes
        self.cache.set(cache_key, roles, ttl=120)
        return roles
    
    def has_permission(self, user_id: int, permission: Permission) -> bool:
        """بررسی دسترسی کاربر (از تمام نقش‌ها)"""
        roles = self.get_user_roles(user_id)
        if not roles:
            return False
        
        # اگر حداقل یکی از نقش‌ها دسترسی داشته باشد
        return any(role.has_permission(permission) for role in roles)
    
    def get_user_permissions(self, user_id: int) -> Set[Permission]:
        """دریافت تمام دسترسی‌های کاربر (ترکیب از تمام نقش‌ها) با cache کوتاه‌مدت"""
        cache_key = f"user_perms_{user_id}"
        cached_perms = self.cache.get(cache_key)
        if cached_perms is not None:
            return cached_perms

        roles = self.get_user_roles(user_id)
        if not roles:
            perms: Set[Permission] = set()
            self.cache.set(cache_key, perms, ttl=120)
            return perms
        
        # ترکیب permissions از تمام نقش‌ها
        all_permissions: Set[Permission] = set()
        for role in roles:
            all_permissions.update(role.permissions)
        # Cache for 2 minutes
        self.cache.set(cache_key, all_permissions, ttl=120)
        return all_permissions
    
    def get_role_permissions(self, role_name: str) -> Set[Permission]:
        """
        دریافت دسترسی‌های یک نقش (برای backward compatibility)
        
        Args:
            role_name: نام نقش (مثلاً 'super_admin', 'br_admin')
            
        Returns:
            Set of permissions for the role
        """
        role = self.get_role(role_name)
        if role:
            return role.permissions
        return set()
    
    def is_admin(self, user_id: int) -> bool:
        """بررسی اینکه آیا کاربر ادمین است یا نه"""
        return self.db.is_admin(user_id)
    
    def is_super_admin(self, user_id: int) -> bool:
        """بررسی اینکه آیا کاربر super admin است یا نه"""
        role_names = self.db.get_admin_roles(user_id)
        return 'super_admin' in role_names
    
    def get_admin_list(self) -> List[Dict]:
        """دریافت لیست تمام ادمین‌ها"""
        return self.db.get_all_admins()
    
    def get_mode_permissions(self, user_id: int) -> List[str]:
        """
        دریافت لیست مودهایی که کاربر به آن‌ها دسترسی دارد
        Returns: ['br', 'mp'] یا ['br'] یا ['mp'] یا []
        """
        permissions = self.get_user_permissions(user_id)
        modes = []
        
        # بررسی دسترسی به اتچمنت BR/MP
        if Permission.MANAGE_ATTACHMENTS_BR in permissions:
            modes.append('br')
        if Permission.MANAGE_ATTACHMENTS_MP in permissions:
            modes.append('mp')
        
        return modes
    
    def get_guide_mode_permissions(self, user_id: int) -> List[str]:
        """
        دریافت لیست مودهایی که کاربر به تنظیمات آن‌ها دسترسی دارد
        Returns: ['br', 'mp'] یا ['br'] یا ['mp'] یا []
        """
        permissions = self.get_user_permissions(user_id)
        modes = []
        
        # بررسی دسترسی به تنظیمات بازی BR/MP
        if Permission.MANAGE_GUIDES_BR in permissions or Permission.MANAGE_SETTINGS in permissions:
            modes.append('br')
        if Permission.MANAGE_GUIDES_MP in permissions or Permission.MANAGE_SETTINGS in permissions:
            modes.append('mp')
        
        return modes


# ========== Decorators ==========

def require_admin(func):
    """Decorator برای محدود کردن دسترسی به ادمین‌ها"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        # بررسی دسترسی ادمین
        if not hasattr(self, 'role_manager'):
            # fallback به سیستم قدیمی
            from config import ADMIN_IDS
            if user_id not in ADMIN_IDS:
                if update.callback_query:
                    await update.callback_query.answer("❌ شما دسترسی ادمین ندارید.", show_alert=True)
                else:
                    await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")
                return None
        else:
            if not self.role_manager.is_admin(user_id):
                if update.callback_query:
                    await update.callback_query.answer("❌ شما دسترسی ادمین ندارید.", show_alert=True)
                else:
                    await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")
                return None
        
        return await func(self, update, context, *args, **kwargs)
    
    return wrapper


def require_permission(*required_permissions: Permission):
    """
    Decorator برای محدود کردن دسترسی به کاربران با دسترسی‌های خاص
    
    Usage:
        @require_permission(Permission.MANAGE_ATTACHMENTS_BR)
        async def some_handler(self, update, context):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            
            # بررسی وجود role_manager
            if not hasattr(self, 'role_manager'):
                logger.error("role_manager not found in handler class")
                if update.callback_query:
                    await update.callback_query.answer("❌ خطای سیستم", show_alert=True)
                else:
                    await update.message.reply_text("❌ خطای سیستم")
                return None
            
            # بررسی اینکه کاربر ادمین است
            if not self.role_manager.is_admin(user_id):
                if update.callback_query:
                    await update.callback_query.answer("❌ شما دسترسی ادمین ندارید.", show_alert=True)
                else:
                    await update.message.reply_text("❌ شما دسترسی ادمین ندارید.")
                return None
            
            # بررسی دسترسی‌ها
            user_permissions = self.role_manager.get_user_permissions(user_id)
            
            # اگر super_admin است، همه دسترسی‌ها را دارد
            if self.role_manager.is_super_admin(user_id):
                return await func(self, update, context, *args, **kwargs)
            
            # بررسی اینکه حداقل یکی از دسترسی‌های مورد نیاز را دارد
            has_permission = any(perm in user_permissions for perm in required_permissions)
            
            if not has_permission:
                permission_names = [p.value for p in required_permissions]
                logger.warning(f"User {user_id} tried to access {func.__name__} without permission: {permission_names}")
                
                if update.callback_query:
                    await update.callback_query.answer("❌ شما دسترسی به این بخش را ندارید.", show_alert=True)
                else:
                    await update.message.reply_text("❌ شما دسترسی به این بخش را ندارید.")
                return None
            
            return await func(self, update, context, *args, **kwargs)
        
        return wrapper
    return decorator


def require_super_admin(func):
    """Decorator برای محدود کردن دسترسی به super admin فقط"""
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        
        if not hasattr(self, 'role_manager'):
            logger.error("role_manager not found in handler class")
            if update.callback_query:
                await update.callback_query.answer("❌ خطای سیستم", show_alert=True)
            else:
                await update.message.reply_text("❌ خطای سیستم")
            return None
        
        if not self.role_manager.is_super_admin(user_id):
            if update.callback_query:
                await update.callback_query.answer("❌ فقط ادمین کل به این بخش دسترسی دارد.", show_alert=True)
            else:
                await update.message.reply_text("❌ فقط ادمین کل به این بخش دسترسی دارد.")
            return None
        
        return await func(self, update, context, *args, **kwargs)
    
    return wrapper


# ========== Helper Functions ==========

def get_permission_display_name(permission: Permission) -> str:
    """دریافت نام فارسی دسترسی"""
    names = {
        Permission.MANAGE_ATTACHMENTS_BR: "🪂 مدیریت اتچمنت BR",
        Permission.MANAGE_ATTACHMENTS_MP: "🎮 مدیریت اتچمنت MP",
        Permission.MANAGE_USER_ATTACHMENTS: "🎮 مدیریت اتچمنت کاربران",
        Permission.MANAGE_SUGGESTED_ATTACHMENTS: "💡 مدیریت پیشنهادی‌ها",
        Permission.MANAGE_GUIDES_BR: "🪂 مدیریت راهنماهای BR",
        Permission.MANAGE_GUIDES_MP: "🎮 مدیریت راهنماهای MP",
        Permission.MANAGE_TEXTS: "📝 مدیریت متون",
        Permission.MANAGE_CMS: "📰 مدیریت CMS",
        Permission.MANAGE_CHANNELS: "🔐 مدیریت کانال‌ها",
        Permission.MANAGE_ADMINS: "👥 مدیریت ادمین‌ها",
        Permission.MANAGE_CATEGORIES: "🗂 مدیریت دسته‌ها",
        Permission.MANAGE_SETTINGS: "⚙️ مدیریت تنظیمات",
        Permission.SEND_NOTIFICATIONS: "📣 ارسال نوتیفیکیشن",
        Permission.MANAGE_NOTIFICATION_SETTINGS: "🔧 تنظیمات نوتیف",
        Permission.MANAGE_SCHEDULED_NOTIFICATIONS: "⏱ مدیریت زمان‌بندی اعلان‌ها",
        Permission.MANAGE_TICKETS: "🎟️ مدیریت تیکت‌ها",
        Permission.MANAGE_FAQS: "❓ مدیریت FAQ",
        Permission.VIEW_FEEDBACK: "💬 مشاهده بازخوردها",
        Permission.VIEW_ANALYTICS: "📊 مشاهده آمار",
        Permission.BACKUP_DATA: "💾 بکاپ‌گیری",
        Permission.IMPORT_EXPORT: "📥📤 Import/Export",
        Permission.VIEW_HEALTH_REPORTS: "🧪 گزارش سلامت داده",
        Permission.RUN_HEALTH_CHECKS: "🧰 اجرای چک‌های سلامت",
        Permission.FIX_DATA_ISSUES: "🛠️ رفع مشکلات داده",
    }
    # اگر mapping نبود، fallback امن بدون underscore برای Markdown
    if permission in names:
        return names[permission]
    # Escape underscores to prevent Telegram Markdown parse errors
    safe_value = permission.value.replace('_', '\\_')
    return safe_value


def format_permissions_list(permissions: Set[Permission]) -> str:
    """فرمت کردن لیست دسترسی‌ها برای نمایش"""
    if not permissions:
        return "هیچ دسترسی"
    
    return "\n".join([f"  • {get_permission_display_name(p)}" for p in sorted(permissions, key=lambda x: x.value)])
