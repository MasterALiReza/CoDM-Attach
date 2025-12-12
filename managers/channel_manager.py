"""
مدیریت کانال‌های اجباری برای عضویت
این ماژول مسئول مدیریت و بررسی عضویت اجباری کاربران در کانال‌ها است
"""
from functools import wraps
from typing import Dict, List, Tuple
from collections import OrderedDict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import ContextTypes
from telegram.constants import ChatMemberStatus
from utils.logger import get_logger, log_exception, log_execution
from utils.language import get_user_lang, ensure_language
from utils.i18n import t, kb
from config.config import DEFAULT_LANG, LANGUAGE_ONBOARDING
logger = get_logger('channel', 'channel.log')
import asyncio
from datetime import datetime, timedelta
from utils.analytics_pg import AnalyticsPostgres as Analytics
from core.security.rate_limiter import rate_limiter, RateLimit


# ✅ Smart Cache با LRU و Size Limit برای Memory Safety
_membership_cache = OrderedDict()  # OrderedDict برای LRU eviction
MAX_CACHE_SIZE = 10000  # حداکثر 10K کاربر در cache (جلوگیری از memory leak)
MEMBER_CACHE_DURATION = timedelta(minutes=30)  # کاربران عضو: 30 دقیقه
NON_MEMBER_CACHE_DURATION = timedelta(minutes=2)  # کاربران غیرعضو: 2 دقیقه


def clean_expired_cache():
    """پاک کردن cache‌های منقضی شده با TTL متغیر"""
    global _membership_cache
    now = datetime.now()
    expired_keys = []
    
    for user_id, (is_member, timestamp) in _membership_cache.items():
        # TTL متغیر بر اساس وضعیت عضویت
        ttl = MEMBER_CACHE_DURATION if is_member else NON_MEMBER_CACHE_DURATION
        if now - timestamp >= ttl:
            expired_keys.append(user_id)
    
    for key in expired_keys:
        del _membership_cache[key]
    
    if expired_keys:
        logger.debug(f"تعداد {len(expired_keys)} cache منقضی شده پاک شد")
    
    return len(expired_keys)


def _add_to_cache(user_id: int, is_member: bool):
    """✅ اضافه کردن به cache با LRU eviction برای جلوگیری از memory leak"""
    global _membership_cache
    
    # اگر cache پر شده، قدیمی‌ترین را حذف کن (LRU)
    if len(_membership_cache) >= MAX_CACHE_SIZE:
        # popitem(last=False) قدیمی‌ترین را حذف می‌کند
        oldest_user, oldest_data = _membership_cache.popitem(last=False)
        logger.debug(f"Cache full ({MAX_CACHE_SIZE}), evicted oldest user: {oldest_user}")
    
    # اضافه کردن user جدید
    _membership_cache[user_id] = (is_member, datetime.now())
    
    # انتقال به آخر (mark as recently used)
    _membership_cache.move_to_end(user_id)


def invalidate_user_cache(user_id: int):
    """پاک کردن cache یک کاربر خاص"""
    global _membership_cache
    if user_id in _membership_cache:
        del _membership_cache[user_id]
        logger.debug(f"Cache کاربر {user_id} پاک شد")


def invalidate_all_cache():
    """پاک کردن cache تمام کاربران (وقتی کانال add/remove میشه)"""
    global _membership_cache
    count = len(_membership_cache)
    _membership_cache.clear()
    logger.info(f"Cache تمام کاربران پاک شد ({count} کاربر)")
    return count


class ChannelManager:
    """مدیریت کانال‌های اجباری"""
    
    def __init__(self, db):  # DatabaseAdapter
        self.db = db
    
    async def _check_single_channel(self, user_id: int, channel: Dict[str, str], bot) -> tuple[bool, Dict[str, str]]:
        """
        بررسی عضویت کاربر در یک کانال خاص
        
        این تابع helper برای بررسی موازی (asyncio.gather) طراحی شده است.
        
        Args:
            user_id: شناسه کاربر تلگرام
            channel: دیکشنری حاوی اطلاعات کانال (channel_id, title, url)
            bot: instance ربات برای فراخوانی API
        
        Returns:
            tuple: (is_member, channel_dict)
                - is_member: True اگر کاربر عضو باشد
                - channel_dict: همان دیکشنری کانال ورودی
        
        Note:
            در صورت خطای شبکه، خطا به لایه بالاتر ارسال می‌شود تا پیام مناسب (مثلاً retry) نمایش داده شود
        """
        try:
            # تبدیل channel_id به int اگر string است
            channel_id = channel['channel_id']
            if isinstance(channel_id, str):
                if not channel_id.startswith('@'):
                    try:
                        channel_id = int(channel_id)
                    except ValueError:
                        pass
            
            member = await bot.get_chat_member(
                chat_id=channel_id,
                user_id=user_id
            )
            
            logger.info(f"کاربر {user_id} در کانال {channel['title']}: status={member.status}")
            
            # بررسی وضعیت عضویت
            if member.status in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER
            ]:
                logger.info(f"کاربر {user_id} عضو کانال {channel['title']} است")
                return True, channel
            else:
                logger.warning(f"کاربر {user_id} عضو کانال {channel['title']} نیست (status={member.status})")
                return False, channel
        
        except Exception as e:
            error_type = type(e).__name__
            logger.error(f"خطا در بررسی عضویت کانال {channel.get('channel_id', 'unknown')} ({channel.get('title', 'unknown')}): {error_type}: {e}")
            
            # خطاهای شبکه به لایه بالاتر پاس داده می‌شوند تا هندلر بتواند پیام مناسب (network error) نشان دهد
            if "ConnectError" in error_type or "NetworkError" in error_type or "TimedOut" in error_type:
                raise
            # سایر خطاها به عنوان عدم عضویت تفسیر می‌شوند (fail-closed برای گیت عضویت)
            return False, channel

    async def check_user_membership(self, user_id: int, bot, use_cache: bool = True) -> Tuple[bool, List[Dict[str, str]]]:
        """
        بررسی عضویت کاربر در همه کانال‌های اجباری با cache و بررسی موازی
        
        Args:
            user_id: شناسه کاربر
            bot: نمونه ربات
            use_cache: استفاده از cache (پیش‌فرض True)
        
        Returns:
            tuple: (is_member_of_all, list_of_not_joined_channels)
        """
        global _membership_cache
        
        # پاکسازی cache‌های منقضی شده (هر 10 بار یک بار)
        if len(_membership_cache) > 0 and user_id % 10 == 0:
            clean_expired_cache()
        
        # بررسی Smart Cache با TTL متغیر
        if use_cache and user_id in _membership_cache:
            is_member, timestamp = _membership_cache[user_id]
            now = datetime.now()
            
            # TTL بر اساس وضعیت
            ttl = MEMBER_CACHE_DURATION if is_member else NON_MEMBER_CACHE_DURATION
            
            if now - timestamp < ttl:
                logger.debug(f"استفاده از cache برای کاربر {user_id} (TTL={'30m' if is_member else '2m'})")
                # عضوها: cache طولانی مدت (30 دقیقه) بدون re-check
                if is_member:
                    return True, []
                # غیرعضوها: دوباره چک کن (شاید عضو شده‌اند) - اما cache کوتاه‌مدت
                # برای non-members هم اگر تو TTL باشن برگردون (2 دقیقه)
                return False, []  # برای non-member هم از cache استفاده کن
        
        # فقط کانال‌های فعال رو چک می‌کنیم
        channels = self.db.get_required_channels()
        
        if not channels:
            _add_to_cache(user_id, True)
            return True, []
        
        # بررسی موازی همه کانال‌ها با asyncio.gather برای سرعت بیشتر
        tasks = [self._check_single_channel(user_id, channel, bot) for channel in channels]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # پردازش نتایج
        not_joined = []
        network_exc = None
        for result in results:
            if isinstance(result, Exception):
                error_type = type(result).__name__
                logger.error(f"خطا در بررسی موازی: {error_type}: {result}")
                # خطاهای شبکه برای نمایش پیام retry به لایه بالاتر پاس داده می‌شوند
                if "ConnectError" in error_type or "NetworkError" in error_type or "TimedOut" in error_type:
                    network_exc = result
                    continue
                # سایر خطاها به صورت استثنا بالا می‌روند تا global error handler آن‌ها را مدیریت کند
                raise result
            
            is_member, channel = result
            if not is_member:
                not_joined.append(channel)

        # اگر حداقل یک خطای شبکه رخ داده، آن را به لایه بالاتر پاس بده تا پیام مناسب نمایش داده شود
        if network_exc is not None:
            raise network_exc
        
        # ذخیره در cache با LRU management
        is_all_member = len(not_joined) == 0
        _add_to_cache(user_id, is_all_member)
        
        return is_all_member, not_joined
    
    def create_join_keyboard(self, channels: List[Dict[str, str]], lang: str = 'fa') -> InlineKeyboardMarkup:
        """
        ایجاد کیبورد inline با دکمه‌های عضویت در کانال‌ها
        
        Args:
            channels: لیست کانال‌های اجباری که کاربر باید عضو شود
        
        Returns:
            InlineKeyboardMarkup: کیبورد شامل دکمه‌های عضویت و بررسی
        """
        keyboard = []
        
        for channel in channels:
            keyboard.append([
                InlineKeyboardButton(
                    t("membership.cta.join", lang, title=channel['title']),
                    url=channel['url']
                )
            ])
        
        # دکمه بررسی مجدد
        keyboard.append([
            InlineKeyboardButton(t("membership.cta.joined", lang), callback_data="check_membership")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    def create_membership_message(self, channels: List[Dict[str, str]], is_first_time: bool = True, lang: str = 'fa') -> str:
        """
        ایجاد پیام فارسی برای درخواست عضویت در کانال‌ها
        
        Args:
            channels: لیست کانال‌هایی که کاربر باید عضو شود
            is_first_time: آیا این اولین بار است که کاربر این پیام را می‌بیند؟
        
        Returns:
            str: پیام HTML با لیست کانال‌ها و دستورالعمل‌ها
        """
        if is_first_time:
            message = t("membership.title.first", lang, app_name=t("app.name", lang)) + "\n\n"
            message += t("membership.body", lang) + "\n\n"
        else:
            message = t("membership.title.reminder", lang) + "\n\n"
            message += t("membership.body", lang) + "\n\n"
        
        for i, channel in enumerate(channels, 1):
            message += t("membership.list.item", lang, i=i, title=channel['title']) + "\n"
        
        cta = t("membership.cta.joined", lang)
        message += "\n" + t("membership.footer", lang, cta=cta)
        
        return message


def require_channel_membership(func):
    """
    دکوریتور برای بررسی عضویت اجباری در کانال‌ها
    """
    @wraps(func)
    async def wrapper(self_or_update, update_or_context=None, context=None, *args, **kwargs):
        # بررسی اینکه آیا این یک method است یا function
        if update_or_context is None:
            # این یک function است (نه method)
            update = self_or_update
            context = context if context else args[0] if args else None
        else:
            # این یک method است
            self = self_or_update
            update = update_or_context
            if context is None:
                context = args[0] if args else None
        
        # بررسی وجود user_id
        if update.effective_user:
            user_id = update.effective_user.id
        else:
            if update_or_context is None:
                return await func(update, context, *args, **kwargs)
            else:
                return await func(self, update, context, *args, **kwargs)
        
        # استثناء: اگر CallbackQuery از یک گروه/سوپرگروه است، بررسی عضویت را رد کن
        # این مورد برای دکمه‌های فیدبک پیام‌های اینلاین در گروه‌ها لازم است
        try:
            chat_type = update.effective_chat.type if update.effective_chat else None
        except Exception:
            chat_type = None
        if update.callback_query and chat_type in ("group", "supergroup"):
            if update_or_context is None:
                return await func(update, context, *args, **kwargs)
            else:
                return await func(self, update, context, *args, **kwargs)
        
        # دریافت database از context
        db = context.bot_data.get('database') if context and hasattr(context, 'bot_data') else None
        if not db:
            logger.error("Database not found in bot_data")
            # در صورت نبود دیتابیس، به‌جای باز گذاشتن گیت، پیام خطا نمایش داده می‌شود
            lang = DEFAULT_LANG
            try:
                if getattr(update, 'callback_query', None):
                    await update.callback_query.answer()
                    await update.callback_query.message.reply_text(t('error.generic', lang))
                elif getattr(update, 'message', None):
                    await update.message.reply_text(t('error.generic', lang))
            except Exception as e:
                logger.error(f"Failed to send membership error message when database is missing: {e}")
            return None
        
        # قبل از گیت عضویت: در صورت فعال بودن onboarding، اطمینان از انتخاب زبان کاربر
        if LANGUAGE_ONBOARDING:
            try:
                ok = await ensure_language(update, context, db)
                if not ok:
                    return None
            except Exception as e:
                # در صورت بروز خطا در i18n، ادامه می‌دهیم تا جریان قطع نشود اما خطا را لاگ می‌کنیم
                logger.error(f"Error during language onboarding: {e}")
        
        # ایجاد ChannelManager
        channel_manager = ChannelManager(db)
        
        # بررسی عضویت
        is_member, not_joined = await channel_manager.check_user_membership(
            user_id, 
            context.bot
        )
        
        # اگر عضو همه کانال‌ها است، ادامه بده
        if is_member:
            if update_or_context is None:
                return await func(update, context, *args, **kwargs)
            else:
                return await func(self, update, context, *args, **kwargs)
        
        # ارسال پیام عضویت اجباری
        # اگر از طریق پیام است (مثل /start)، پیام خوش‌آمدگویی نشان بده
        is_first_time = update.message is not None
        # زبان کاربر برای محلی‌سازی پیام‌ها
        try:
            lang = get_user_lang(update, context, db) or DEFAULT_LANG
        except Exception:
            lang = DEFAULT_LANG
        message = channel_manager.create_membership_message(not_joined, is_first_time=is_first_time, lang=lang)
        keyboard = channel_manager.create_join_keyboard(not_joined, lang=lang)
        
        if update.callback_query:
            await update.callback_query.message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        elif update.message:
            await update.message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode='HTML'
            )
        
        return None
    
    return wrapper


async def _track_join_success(user_id: int, channels: list):
    """
    ثبت آمار عضویت موفق در background (async)
    این تابع UI رو block نمی‌کنه
    """
    try:
        analytics = Analytics()
        for channel in channels:
            analytics.track_join_success(user_id, channel['channel_id'])
        logger.debug(f"Analytics: Tracked join success for user {user_id}")
    except Exception as e:
        logger.error(f"[Analytics] Error in background tracking: {e}")


async def _send_main_menu(query, context: ContextTypes.DEFAULT_TYPE, db, user_id: int):
    """ارسال منوی اصلی به کاربر بعد از تایید عضویت
    این تابع کیبورد منو را می‌سازد و برای کاربر ارسال می‌کند
    """
    from telegram import ReplyKeyboardMarkup
    from utils.subscribers_pg import SubscribersPostgres as Subscribers
    
    # ثبت کاربر برای نوتیفیکیشن
    try:
        subs = Subscribers()
        subs.add(user_id)
    except Exception as e:
        logger.warning(f"Error registering user {user_id} for notifications: {e}")
    
    # تعیین زبان کاربر
    try:
        lang = db.get_user_language(user_id) or DEFAULT_LANG
    except Exception:
        lang = DEFAULT_LANG
    
    # ساخت کیبورد منوی اصلی (محلی‌سازی شده)
    keyboard = [
        [kb("menu.buttons.game_settings", lang), kb("menu.buttons.get", lang)]
    ]
    
    # بررسی فعال بودن سیستم اتچمنت کاربران
    try:
        ua_system_enabled = db.get_ua_setting('system_enabled') or '1'
        logger.info(f"[DEBUG channel_manager] UA system_enabled: {repr(ua_system_enabled)}")
        if ua_system_enabled in ('1', 'true', 'True'):
            keyboard.append([kb("menu.buttons.ua", lang), kb("menu.buttons.suggested", lang)])
        else:
            keyboard.append([kb("menu.buttons.suggested", lang)])
    except Exception as e:
        # در صورت خطا، UA رو نشون نده
        logger.error(f"[ERROR] Exception in UA button check: {e}", exc_info=True)
        keyboard.append([kb("menu.buttons.suggested", lang)])
    
    keyboard.extend([
        [kb("menu.buttons.season_list", lang), kb("menu.buttons.season_top", lang)],
        [kb("menu.buttons.notify", lang), kb("menu.buttons.search", lang)],
        [kb("menu.buttons.contact", lang), kb("menu.buttons.help", lang)]
    ])
    
    # دکمه تنظیمات ربات (کاربر)
    keyboard.append([kb("menu.buttons.user_settings", lang)])

    # اگر کاربر ادمین است، دکمه پنل ادمین را اضافه کن
    try:
        if db.is_admin(user_id):
            keyboard.append([kb("menu.buttons.admin", lang)])
    except Exception:
        pass
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    # حذف پیام قبلی (عضویت تایید شد) برای جلوگیری از loading stuck
    try:
        await query.message.delete()
    except Exception:
        pass
    
    # ارسال پیام خوش‌آمدگویی با منوی کیبورد
    welcome_text = t("welcome", lang, app_name=t("app.name", lang))
    await context.bot.send_message(
        chat_id=user_id,
        text=welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    logger.info(f"✅ Main menu sent to user {user_id} after membership verification")


async def check_membership_callback(update, context: ContextTypes.DEFAULT_TYPE):
    """
    هندلر برای بررسی مجدد عضویت کاربر در کانال‌های اجباری
    
    این تابع زمانی فراخوانی می‌شود که کاربر روی دکمه "✅ عضو شدم" کلیک می‌کند.
    عملیات:
    - Rate limiting: جلوگیری از API flood
    - Invalidate کردن cache کاربر
    - بررسی موازی عضویت در تمام کانال‌ها
    - ثبت آمار (analytics)
    - نمایش منوی اصلی در صورت موفقیت
    """
    query = update.callback_query
    user_id = update.effective_user.id
    # Determine language as early as possible (fallback to DEFAULT_LANG)
    try:
        lang = context.user_data.get('_lang') or DEFAULT_LANG
    except Exception:
        lang = DEFAULT_LANG
    
    # Rate Limiting: جلوگیری از spam/flood
    # محدودیت: 3 درخواست در 10 ثانیه برای هر کاربر
    user_check_limit = RateLimit(calls=3, period=10)
    is_allowed, wait_time = await rate_limiter.check_rate_limit(f"membership_check_{user_id}", user_check_limit)
    
    if not is_allowed:
        await query.answer(
            t('rate_limit.wait_seconds', lang, seconds=int(wait_time)),
            show_alert=True
        )
        logger.warning(f"Rate limit hit for user {user_id} - wait {wait_time:.1f}s")
        return

    await query.answer(t('membership.checking', lang))
    
    # پاک کردن cache کاربر قبل از بررسی (چون تازه عضو شده)
    invalidate_user_cache(user_id)
    
    db = context.bot_data.get('database')
    channel_manager = ChannelManager(db)
    
    # بررسی عضویت (cache قبلاً invalidate شده)
    is_member = False
    not_joined = []
    network_error = False
    all_channels = []
    
    try:
        # دریافت لیست کانال‌ها برای analytics
        all_channels = db.get_active_channels()
        
        # بررسی عضویت
        is_member, not_joined = await channel_manager.check_user_membership(
            user_id,
            context.bot
        )
    except Exception as e:
        # اگر خطای اتصال رخ داد
        error_type = type(e).__name__
        if "ConnectError" in error_type or "NetworkError" in error_type or "TimedOut" in error_type:
            network_error = True
            logger.error(f"خطای اتصال در بررسی عضویت کاربر {user_id}: {e}")
        else:
            raise
    
    if network_error:
        # Connection error — localized message with retry action
        await query.message.edit_text(
            t('membership.network_error.title', lang) + "\n\n" + t('membership.network_error.body', lang),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(t('common.retry', lang), callback_data="check_membership")
            ]]),
            parse_mode='HTML'
        )
    elif is_member:
        # ارسال منوی اصلی فوراً (بدون تاخیر - اولویت اول)
        await _send_main_menu(query, context, db, user_id)
        
        # Analytics: ثبت عضویت موفق به صورت async در background
        # این کار UI رو block نمی‌کنه
        asyncio.create_task(_track_join_success(user_id, all_channels))
    else:
        # هنوز عضو نشده
        try:
            lang = db.get_user_language(user_id) or DEFAULT_LANG
        except Exception:
            lang = DEFAULT_LANG
        message = channel_manager.create_membership_message(not_joined, is_first_time=False, lang=lang)
        keyboard = channel_manager.create_join_keyboard(not_joined, lang=lang)
        
        await query.message.edit_text(
            message,
            reply_markup=keyboard,
            parse_mode='HTML'
        )
