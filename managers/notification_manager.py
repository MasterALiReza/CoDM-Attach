"""
مدیریت نوتیفیکیشن‌های کاربران و ترکیب پیام‌ها
"""

import asyncio
from utils.logger import get_logger, log_exception, log_execution
logger = get_logger('notification', 'notification.log')
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from telegram.ext import ContextTypes
from config.config import NOTIFICATION_SETTINGS, GAME_MODES, DEFAULT_LANG
import json
from utils.broadcast_optimizer import OptimizedBroadcaster
from utils.i18n import t



class NotificationManager:
    """مدیریت و ارسال نوتیفیکیشن‌ها با قابلیت ترکیب پیام‌ها"""
    
    def __init__(self, db, subscribers):
        self.db = db
        self.subscribers = subscribers
        self.pending_notifications = {}  # ذخیره نوتیف‌های در انتظار
        self.batch_delay = 3  # تاخیر 3 ثانیه برای ترکیب پیام‌ها
        self._batch_tasks = {}  # ذخیره task های در حال اجرا
        self.broadcaster = OptimizedBroadcaster(max_concurrent=30, delay_between_batches=1.0)
    
    async def queue_notification(self, context: ContextTypes.DEFAULT_TYPE, 
                                 event_type: str, payload: dict):
        """اضافه کردن نوتیفیکیشن به صف برای ارسال دسته‌ای"""
        
        logger.info(f"[NotifManager] Queue notification: {event_type} - Payload: {payload}")
        
        # بررسی وضعیت کلی سیستم
        if not NOTIFICATION_SETTINGS.get('enabled', True):
            logger.info(f"[NotifManager] System disabled, skipping")
            return
        
        # بررسی فعال بودن این نوع رویداد
        if not NOTIFICATION_SETTINGS.get('events', {}).get(event_type, False):
            logger.info(f"[NotifManager] Event {event_type} disabled, skipping")
            return
        
        # کلید یکتا برای گروه‌بندی نوتیف‌ها
        category = payload.get('category', '')
        weapon = payload.get('weapon', '')
        code = payload.get('code', '')
        mode = payload.get('mode', 'br')
        
        group_key = f"{category}_{weapon}_{code}_{mode}"
        
        # ایجاد گروه جدید یا افزودن به گروه موجود
        if group_key not in self.pending_notifications:
            self.pending_notifications[group_key] = {
                'base_info': {
                    'category': category,
                    'weapon': weapon,
                    'code': code,
                    'mode': mode,
                    'name': payload.get('name', '')
                },
                'events': [],
                'timestamp': datetime.now()
            }
        
        # اضافه کردن رویداد به گروه
        self.pending_notifications[group_key]['events'].append({
            'type': event_type,
            'payload': payload
        })
        
        # لغو task قبلی اگر وجود داشت
        if group_key in self._batch_tasks:
            self._batch_tasks[group_key].cancel()
        
        # ایجاد task جدید برای ارسال بعد از تاخیر
        task = asyncio.create_task(
            self._send_batch_notification(context, group_key)
        )
        self._batch_tasks[group_key] = task
    
    async def _send_batch_notification(self, context: ContextTypes.DEFAULT_TYPE, 
                                      group_key: str):
        """ارسال نوتیفیکیشن ترکیبی بعد از تاخیر"""
        try:
            # تاخیر برای جمع‌آوری رویدادهای بیشتر
            await asyncio.sleep(self.batch_delay)
            
            if group_key not in self.pending_notifications:
                return
            
            group = self.pending_notifications[group_key]
            base_info = group['base_info']
            events = group['events']
            
            # دریافت لیست کاربران با تنظیمات فعال
            active_users = await self._get_active_users_for_events(
                [e['type'] for e in events],
                base_info['mode']
            )

            logger.info(f"[NotifManager] Active users count: {len(active_users)}")

            if active_users:
                # گروه‌بندی کاربران بر اساس زبان برای ارسال پیام چندزبانه
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                lang_to_users: Dict[str, Set[int]] = {}
                for user_id in active_users:
                    user_lang = None
                    try:
                        user_lang = self.db.get_user_language(user_id)
                    except Exception as e:
                        logger.error(f"[NotifManager] Error getting language for user {user_id}: {e}")
                    if not user_lang:
                        user_lang = DEFAULT_LANG
                    lang_to_users.setdefault(user_lang, set()).add(user_id)

                # callback_data format: attm__{category}__{weapon}__{code}__{mode}
                # استفاده از __ به عنوان separator برای جلوگیری از تداخل با underscore در مقادیر
                callback_data = f"attm__{base_info['category']}__{base_info['weapon']}__{base_info['code']}__{base_info['mode']}"

                for lang, users in lang_to_users.items():
                    # ساخت پیام ترکیبی برای هر زبان
                    message = await self._build_combined_message(base_info, events, lang=lang)
                    logger.info(f"[NotifManager] Built message ({lang}): {message[:100] if message else 'None'}...")

                    if not message:
                        continue

                    button_text = t("notification.view_attachment", lang)
                    keyboard = [[InlineKeyboardButton(button_text, callback_data=callback_data)]]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    # ارسال پیام به کاربران این زبان
                    await self._broadcast_to_users(context, message, users, reply_markup)
            
            # حذف از صف
            del self.pending_notifications[group_key]
            del self._batch_tasks[group_key]
            
        except asyncio.CancelledError:
            # task لغو شده، چیزی نکن
            pass
        except Exception as e:
            logger.error(f"Error sending batch notification: {e}")
            log_exception(logger, e, "context")
    
    async def _build_combined_message(self, base_info: dict,
                                     events: List[dict],
                                     lang: str = 'fa') -> Optional[str]:
        """ساخت پیام ترکیبی از چند رویداد با در نظر گرفتن زبان کاربر"""
        
        if not events:
            return None
        
        # اگر فقط یک رویداد است
        if len(events) == 1:
            event = events[0]
            template_value = NOTIFICATION_SETTINGS.get('templates', {}).get(event['type'])
            if not template_value:
                return None

            # اضافه کردن نام دسته و مود به payload
            payload = event['payload'].copy()
            from config import WEAPON_CATEGORIES
            cat_key = payload.get('category')
            payload['category_name'] = WEAPON_CATEGORIES.get(cat_key, cat_key)

            # اضافه کردن نام مود با استفاده از i18n
            mode = payload.get('mode', 'br')
            mode_short_key = f"mode.{mode}_short"
            try:
                mode_name = t(mode_short_key, lang)
            except Exception:
                mode_name = GAME_MODES.get(mode, mode)
            payload['mode_name'] = mode_name

            # اگر مقدار template یک کلید i18n باشد، از t() استفاده می‌کنیم؛ در غیر این صورت آن را به عنوان متن قالب در نظر می‌گیریم
            if isinstance(template_value, str) and template_value.startswith("notification.template."):
                return t(template_value, lang, **payload)

            try:
                return template_value.format(**payload)
            except Exception as e:
                log_exception(logger, e, "format_single_event_template")
                return None

        # ترکیب چند رویداد
        mode = base_info.get('mode', 'br')
        mode_short_key = f"mode.{mode}_short"
        try:
            mode_name = t(mode_short_key, lang)
        except Exception:
            mode_name = GAME_MODES.get(mode, mode)

        header = t("notification.combined.header", lang)
        weapon_line = t("notification.combined.weapon", lang, weapon=base_info.get('weapon', ''))
        attachment_line = t(
            "notification.combined.attachment",
            lang,
            name=base_info.get('name', ''),
            code=base_info.get('code', ''),
        )
        mode_line = t("notification.combined.mode", lang, mode=mode_name)

        message_parts = [
            f"{header}\n",
            f"{weapon_line}\n",
            f"{attachment_line}\n",
            f"{mode_line}\n",
            "━━━━━━━━━━━━━━━\n",
        ]
        
        # دسته‌بندی رویدادها
        changes: List[str] = []
        for event in events:
            event_type = event['type']
            payload = event['payload']

            if event_type == 'edit_name':
                changes.append(
                    t(
                        "notification.change.edit_name",
                        lang,
                        old_name=payload.get('old_name', ''),
                        new_name=payload.get('new_name', ''),
                    )
                )
            elif event_type == 'edit_code':
                changes.append(
                    t(
                        "notification.change.edit_code",
                        lang,
                        old_code=payload.get('old_code', ''),
                        new_code=payload.get('new_code', ''),
                    )
                )
            elif event_type == 'edit_image':
                changes.append(t("notification.change.edit_image", lang))
            elif event_type == 'add_attachment':
                changes.append(t("notification.change.add_attachment", lang))
            elif event_type == 'delete_attachment':
                changes.append(t("notification.change.delete_attachment", lang))
            elif event_type == 'top_added':
                changes.append(t("notification.change.top_added", lang))
            elif event_type == 'top_removed':
                changes.append(t("notification.change.top_removed", lang))
            elif event_type == 'top_set':
                changes.append(t("notification.change.top_set", lang))

        if not changes:
            return ''.join(message_parts)

        # اضافه کردن تغییرات به پیام
        changes_header = t("notification.combined.changes_header", lang)
        message_parts.append(f"{changes_header}\n")
        for change in changes:
            message_parts.append(f"• {change}\n")
        
        return ''.join(message_parts)
    
    async def _get_active_users_for_events(self, event_types: List[str], 
                                          mode: str) -> Set[int]:
        """دریافت کاربرانی که این رویدادها را فعال کرده‌اند (Optimized)"""
        
        start_time = datetime.now()
        
        try:
            # استفاده از متد بهینه دیتابیس اگر وجود داشته باشد
            if hasattr(self.db, 'get_users_for_notification'):
                active_users = self.db.get_users_for_notification(event_types, mode)
                
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(f"[NotifManager] SQL Filter: Found {len(active_users)} users in {duration:.3f}s")
                return active_users
            
            # Fallback به روش قدیمی (کند) اگر متد جدید در دیتابیس نبود
            logger.warning("[NotifManager] Optimized query not found, falling back to Python filtering")
            return await self._get_active_users_for_events_legacy(event_types, mode)
            
        except Exception as e:
            logger.error(f"Error in optimized user fetching: {e}")
            log_exception(logger, e, "get_active_users_optimized")
            return set()

    async def _get_active_users_for_events_legacy(self, event_types: List[str], 
                                          mode: str) -> Set[int]:
        """روش قدیمی فیلترینگ (جهت پشتیبانی)"""
        
        # دریافت همه مشترکین
        all_subscribers = self.subscribers.all()
        
        # فیلتر بر اساس تنظیمات کاربران
        active_users = set()
        
        for user_id in all_subscribers:
            try:
                # دریافت تنظیمات کاربر از دیتابیس
                user_prefs = self.db.get_user_notification_preferences(user_id)
                
                if not user_prefs:
                    active_users.add(user_id)
                    continue
                
                if not user_prefs.get('enabled', True):
                    continue
                
                if mode not in user_prefs.get('modes', ['br', 'mp']):
                    continue
                
                user_events = user_prefs.get('events', {})
                
                has_active_event = False
                for event_type in event_types:
                    if user_events.get(event_type, True):
                        has_active_event = True
                        active_users.add(user_id)
                        break
                
                if has_active_event:
                    pass
                        
            except Exception as e:
                continue
        
        return active_users
    
    async def _broadcast_to_users(self, context: ContextTypes.DEFAULT_TYPE,
                                 message: str, user_ids: Set[int], 
                                 reply_markup=None):
        """ارسال پیام به لیست کاربران با broadcaster بهینه شده"""
        
        # استفاده از OptimizedBroadcaster برای ارسال سریع و موازی
        stats = await self.broadcaster.broadcast_to_users(
            list(user_ids),
            context.bot.send_message,
            text=message,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
        
        # حذف کاربران blocked از لیست subscribers
        for user_id in stats['blocked_users']:
            try:
                self.subscribers.remove(user_id)
                logger.info(f"Removed blocked user {user_id} from subscribers")
            except Exception as e:
                logger.warning(f"Failed to remove blocked user {user_id} from subscribers: {e}")
        
        logger.info(
            f"Notification broadcast completed: {stats['success']}/{stats['total']} successful "
            f"in {stats['duration_seconds']}s ({stats['rate_per_second']}/s)"
        )
    
    def get_user_preferences(self, user_id: int) -> dict:
        """دریافت تنظیمات نوتیفیکیشن کاربر"""
        prefs = self.db.get_user_notification_preferences(user_id)
        
        if not prefs:
            # تنظیمات پیش‌فرض
            return {
                'enabled': True,
                'modes': ['br', 'mp'],
                'events': {
                    'add_attachment': True,
                    'edit_name': True,
                    'edit_image': False,
                    'edit_code': True,
                    'delete_attachment': False,
                    'top_set': True,
                    'top_added': True,
                    'top_removed': False
                }
            }
        
        return prefs
    
    def update_user_preferences(self, user_id: int, preferences: dict) -> bool:
        """به‌روزرسانی تنظیمات نوتیفیکیشن کاربر"""
        return self.db.update_user_notification_preferences(user_id, preferences)
    
    def toggle_user_notifications(self, user_id: int) -> bool:
        """فعال/غیرفعال کردن نوتیفیکیشن‌های کاربر"""
        prefs = self.get_user_preferences(user_id)
        prefs['enabled'] = not prefs.get('enabled', True)
        return self.update_user_preferences(user_id, prefs)
    
    def toggle_user_event(self, user_id: int, event: str) -> bool:
        """فعال/غیرفعال کردن یک رویداد خاص برای کاربر"""
        prefs = self.get_user_preferences(user_id)
        current = prefs.get('events', {}).get(event, True)
        prefs['events'][event] = not current
        return self.update_user_preferences(user_id, prefs)
    
    def toggle_user_mode(self, user_id: int, mode: str) -> bool:
        """فعال/غیرفعال کردن نوتیف برای یک مود خاص"""
        prefs = self.get_user_preferences(user_id)
        modes = prefs.get('modes', ['br', 'mp'])
        
        if mode in modes:
            modes.remove(mode)
        else:
            modes.append(mode)
        
        prefs['modes'] = modes
        return self.update_user_preferences(user_id, prefs)
