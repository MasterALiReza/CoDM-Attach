"""
Attachment Analytics Dashboard
Admin interface for viewing attachment performance analytics

✨ Updated: 2025-01-17
- Added sql_helpers for cross-database date queries
- Ready for PostgreSQL migration
"""

import os
import io
import csv
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode

from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import ADMIN_MENU
from core.security.role_manager import Permission
from core.database.database_adapter import DatabaseAdapter
from utils.attachment_analytics import AttachmentAnalytics
from utils.logger import get_logger
from core.database.sql_helpers import get_date_interval, get_current_date
from utils.i18n import t
from config.config import WEAPON_CATEGORIES
from utils.language import get_user_lang

logger = get_logger('attachments_dashboard', 'admin.log')

ANALYTICS_MENU, VIEW_TRENDING, VIEW_WEAPON_STATS, VIEW_UNDERPERFORMING, SEARCH_ATTACH = range(5)

class AttachmentsDashboardHandler(BaseAdminHandler):
    """Handler for attachment analytics dashboard"""
    
    def __init__(self, db: DatabaseAdapter):
        """Initialize handler"""
        super().__init__(db)
        # role_manager is already created in BaseAdminHandler
        # ✨ Updated: Pass DatabaseAdapter instead of db_path
        self.analytics = AttachmentAnalytics(db)
    
    def _escape_markdown(self, text: str) -> str:
        """
        Escape markdown special characters in text (for Markdown parse mode)
        Only escapes the most problematic characters
        """
        if not text:
            return text
        # Escape only essential markdown characters
        escape_chars = ['_', '*', '[', ']', '`']
        for char in escape_chars:
            text = text.replace(char, f'\\{char}')
        return text
    
    async def _safe_edit_message(self, query, message: str, keyboard, parse_mode=ParseMode.MARKDOWN):
        """
        Safely edit message with error handling for "Message is not modified"
        """
        try:
            await query.edit_message_text(
                message,
                parse_mode=parse_mode,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            # Ignore "Message is not modified" error
            if "message is not modified" not in str(e).lower():
                logger.error(f"Error editing message: {e}")
        
    async def analytics_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Show main analytics menu"""
        query = update.callback_query
        if query:
            await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
            
        # Check permissions
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.VIEW_ANALYTICS):
            await self.send_permission_denied(update, context)
            return ConversationHandler.END
            
        # Get overview statistics
        stats = self._get_overview_stats()
        
        # Build message
        message = t('admin.analytics.menu.title', lang) + "\n\n"
        message += t('admin.analytics.menu.overview.header', lang, days=30) + "\n"
        message += t('admin.analytics.menu.overview.views', lang, n=stats['total_views']) + "\n"
        message += t('admin.analytics.menu.overview.clicks', lang, n=stats['total_clicks']) + "\n"
        message += t('admin.analytics.menu.overview.shares', lang, n=stats['total_shares']) + "\n"
        message += t('admin.analytics.menu.overview.users', lang, n=stats['unique_users']) + "\n"
        message += t('admin.analytics.menu.overview.engagement', lang, rate=f"{stats['engagement_rate']:.1f}") + "\n\n"
        
        message += t('admin.analytics.menu.top.header', lang) + "\n"
        if stats['top_performer']:
            safe_name = self._escape_markdown(stats['top_performer']['name'])
            message += t('admin.analytics.menu.top.most_viewed', lang, name=safe_name, views=stats['top_performer']['views']) + "\n"
        if stats['most_engaging']:
            safe_name = self._escape_markdown(stats['most_engaging']['name'])
            message += t('admin.analytics.menu.top.most_engaging', lang, name=safe_name, rate=f"{stats['most_engaging']['rate']:.1f}") + "\n"
        if stats['highest_rated']:
            safe_name = self._escape_markdown(stats['highest_rated']['name'])
            message += t('admin.analytics.menu.top.highest_rated', lang, name=safe_name, rating=f"{stats['highest_rated']['rating']:.1f}") + "\n"
            
        # Build keyboard (implemented handlers)
        context.user_data.pop('analytics_search_mode', None)
        keyboard = [
            [
                InlineKeyboardButton(t('admin.analytics.buttons.trending', lang), callback_data="analytics_view_trending"),
                InlineKeyboardButton(t('admin.analytics.buttons.underperforming', lang), callback_data="analytics_view_underperforming")
            ],
            [
                InlineKeyboardButton(t('admin.analytics.buttons.weapon_stats', lang), callback_data="analytics_view_weapon_stats"),
                InlineKeyboardButton(t('admin.analytics.buttons.user_behavior', lang), callback_data="analytics_view_user_behavior")
            ],
            [
                InlineKeyboardButton(t('admin.analytics.buttons.daily_report', lang), callback_data="analytics_daily_report"),
                InlineKeyboardButton(t('admin.analytics.buttons.weekly_report', lang), callback_data="analytics_weekly_report")
            ],
            [
                InlineKeyboardButton(t('admin.analytics.buttons.search_attachment', lang), callback_data="analytics_search_attachment"),
                InlineKeyboardButton(t('admin.analytics.buttons.download_report', lang), callback_data="analytics_download_report")
            ],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="admin_menu_return")]
        ]
        
        if query:
            await query.edit_message_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_message(
                update.effective_chat.id,
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        return ADMIN_MENU
        
    def _get_db_connection(self):
        """Helper method to get database connection"""
        if hasattr(self.db, 'get_connection'):
            # Via DatabaseAdapter forwarding to PostgreSQL pool
            return self.db.get_connection()
        else:
            raise RuntimeError("Database connection not available")
    
    def _get_overview_stats(self) -> dict:
        """Get overview statistics"""
        stats = {
            'total_views': 0,
            'total_clicks': 0,
            'total_shares': 0,
            'unique_users': 0,
            'engagement_rate': 0,
            'top_performer': None,
            'most_engaging': None,
            'highest_rated': None
        }
        
        try:
            # Overall metrics
            date_filter = get_date_interval(30)
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 
                        COUNT(CASE WHEN action_type = 'view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type = 'click' THEN 1 END) as clicks,
                        COUNT(CASE WHEN action_type = 'share' THEN 1 END) as shares,
                        COUNT(DISTINCT user_id) as unique_users
                    FROM attachment_metrics
                    WHERE DATE(action_date) >= {date_filter}
                """)
                
                result = cursor.fetchone()
            if result:
                stats['total_views'] = result['views']
                stats['total_clicks'] = result['clicks']
                stats['total_shares'] = result['shares']
                stats['unique_users'] = result['unique_users']
                
                if stats['total_views'] > 0:
                    stats['engagement_rate'] = (float(stats['total_clicks']) / float(stats['total_views'])) * 100
                    
            # Top performer by views (from metrics)
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    WITH v AS (
                        SELECT attachment_id, COUNT(*) AS views
                        FROM attachment_metrics
                        WHERE action_type='view'
                        GROUP BY attachment_id
                    )
                    SELECT a.name, v.views
                    FROM v
                    JOIN attachments a ON a.id = v.attachment_id
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    WHERE v.views > 0
                      AND a.name NOT LIKE '%%Test%%'
                      AND a.name NOT LIKE '%%test%%'
                      AND a.name NOT LIKE '%%تست%%'
                      AND a.code NOT LIKE 'CODE%%'
                      AND a.code NOT LIKE 'DUP%%'
                      AND COALESCE(w.name, '') NOT LIKE '%%Test%%'
                    ORDER BY v.views DESC
                    LIMIT 1
                """)
                top = cursor.fetchone()
            if top:
                stats['top_performer'] = {'name': top['name'], 'views': top['views']}
            
            # Most engaging (best click rate) from metrics
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    WITH agg AS (
                        SELECT attachment_id,
                               COUNT(CASE WHEN action_type='view' THEN 1 END) AS v,
                               COUNT(CASE WHEN action_type='click' THEN 1 END) AS c
                        FROM attachment_metrics
                        GROUP BY attachment_id
                    )
                    SELECT a.name,
                           (CAST(agg.c AS FLOAT) / NULLIF(agg.v, 0)) * 100 AS engagement_rate
                    FROM agg
                    JOIN attachments a ON a.id = agg.attachment_id
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    WHERE agg.v > 0 AND agg.c > 0
                      AND a.name NOT LIKE '%%Test%%'
                      AND a.name NOT LIKE '%%test%%'
                      AND a.name NOT LIKE '%%تست%%'
                      AND a.code NOT LIKE 'CODE%%'
                      AND a.code NOT LIKE 'DUP%%'
                      AND COALESCE(w.name, '') NOT LIKE '%%Test%%'
                    ORDER BY engagement_rate DESC
                    LIMIT 1
                """)
                engaging = cursor.fetchone()
            if engaging:
                stats['most_engaging'] = {'name': engaging['name'], 'rate': engaging['engagement_rate']}
                
            # Highest rated - calculate from user_attachment_engagement
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        a.name,
                        AVG(uae.rating) as avg_rating
                    FROM user_attachment_engagement uae
                    JOIN attachments a ON uae.attachment_id = a.id
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    WHERE uae.rating IS NOT NULL
                    AND a.name NOT LIKE '%%Test%%'
                    AND a.name NOT LIKE '%%test%%'
                    AND a.name NOT LIKE '%%تست%%'
                    AND a.code NOT LIKE 'CODE%%'
                    AND a.code NOT LIKE 'DUP%%'
                    AND COALESCE(w.name, '') NOT LIKE '%%Test%%'
                    GROUP BY a.id, a.name
                    HAVING AVG(uae.rating) > 0
                    ORDER BY avg_rating DESC
                    LIMIT 1
                """)
                
                rated = cursor.fetchone()
            if rated:
                stats['highest_rated'] = {'name': rated['name'], 'rating': rated['avg_rating']}
                
        except Exception as e:
            logger.error(f"Error getting overview stats: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            pass  # Connection auto-closed by context manager
            
        return stats
        
    async def view_trending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """ترندینگ - Real-Time با منطق ساده"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.analytics.loading', lang))
        
        # Add timestamp to prevent "Message is not modified" error
        now = datetime.now().strftime('%H:%M:%S')
        
        message = t('admin.analytics.trending.title', lang) + "\n"
        message += t('admin.analytics.trending.subtitle', lang) + "\n"
        message += t('admin.analytics.trending.updated', lang, time=now) + "\n\n"
        results = []
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                # Try real-time trending first (with growth)
                date_filter_7 = get_date_interval(7)
                date_filter_14 = get_date_interval(14)
                date_filter_8 = get_date_interval(8)
                cursor.execute(f"""
                    WITH week_stats AS (
                        SELECT 
                            attachment_id,
                            COUNT(CASE WHEN CAST(action_date AS DATE) >= {date_filter_7} THEN 1 END) as recent_week,
                            COUNT(CASE WHEN CAST(action_date AS DATE) BETWEEN {date_filter_14} AND {date_filter_8} THEN 1 END) as previous_week
                        FROM attachment_metrics
                        WHERE CAST(action_date AS DATE) >= {date_filter_14}
                        AND action_type = 'view'
                        GROUP BY attachment_id
                        HAVING COUNT(CASE WHEN CAST(action_date AS DATE) >= {date_filter_7} THEN 1 END) > 0
                    ),
                    growth_calc AS (
                        SELECT 
                            attachment_id,
                            recent_week,
                            previous_week,
                            CASE 
                                WHEN previous_week = 0 AND recent_week > 0 THEN 100.0
                                WHEN previous_week > 0 THEN ((recent_week * 1.0 - previous_week) / previous_week * 100)
                                ELSE 0
                            END as growth_rate
                        FROM week_stats
                    )
                    SELECT 
                        a.id,
                        a.name,
                        COALESCE(w.name, 'Unknown') as weapon,
                        gc.recent_week as views,
                        gc.growth_rate
                    FROM growth_calc gc
                    JOIN attachments a ON gc.attachment_id = a.id
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    WHERE gc.growth_rate > 0 OR gc.recent_week >= 5
                    ORDER BY gc.growth_rate DESC, gc.recent_week DESC
                    LIMIT 10
                """)
                
                                
                results = cursor.fetchall()
                
                if results:
                    # Display trending results with growth
                    for i, result in enumerate(results, 1):
                        name = result['name']
                        weapon = result['weapon']
                        views = result['views']
                        growth = result['growth_rate']
                        
                        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else f"{i}."
                        if growth >= 100:
                            icon = "🔥"
                        elif growth >= 50:
                            icon = "📈"
                        else:
                            icon = "📊"
                        safe_name = self._escape_markdown(name)
                        safe_weapon = self._escape_markdown(weapon)
                        message += f"{medal} *{safe_name}*\n"
                        message += t('admin.analytics.lines.weapon', lang, weapon=safe_weapon) + "\n"
                        message += t('admin.analytics.lines.growth', lang, icon=icon, value=f"{growth:+.0f}") + "\n"
                        message += t('admin.analytics.lines.views', lang, value=f"{views:,}") + "\n\n"
                else:
                    message += t('admin.analytics.fallback.no_data', lang) + "\n"
        except Exception as e:
            logger.error(f"Error in view_trending: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            message = t('admin.analytics.trending.error.title', lang) + "\n\n" + t('admin.analytics.trending.error.body', lang)
        finally:
            pass  # Connection auto-closed by context manager

        keyboard = []
        if results:
            for i, r in enumerate(results, 1):
                try:
                    att_id = r['id']
                    title = f"{i}. {r['name']}"
                    keyboard.append([InlineKeyboardButton(title, callback_data=f"weapon_details_{att_id}")])
                except Exception:
                    continue
        keyboard.append([InlineKeyboardButton(t('menu.buttons.refresh', lang), callback_data="refresh_trending")])
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")])
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU

    def _map_category_name_to_label(self, db_name: str) -> str:
        """Map DB category name to English+emoji label from WEAPON_CATEGORIES.
        Falls back to the original DB name if no match is found."""
        try:
            nm = (db_name or '').strip().lower()
            # try exact/contains match against emoji-stripped values
            for key, val in WEAPON_CATEGORIES.items():
                v = (val or '').strip()
                # remove leading emoji and whitespace if present
                parts = v.split(' ', 1)
                no_emoji = parts[1].strip() if len(parts) > 1 else v
                ve = no_emoji.lower()
                if nm == ve or nm in ve or ve in nm:
                    return v
        except Exception:
            pass
        return db_name
    
    async def weapon_stats_select_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Alias برای سازگاری با AdminHandlers: انتخاب مود"""
        return await self.ws_choose_mode(update, context)

    async def weapon_stats_show_results(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Alias برای سازگاری با AdminHandlers: نمایش نتایج دسته انتخاب‌شده"""
        return await self.ws_choose_category(update, context)

    async def search_attachment_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمایش UI جستجوی آمار اتچمنت و ورود به حالت دریافت متن"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        if query:
            await query.answer()
            message = t('admin.analytics.search.title', lang) + "\n\n"
            message += t('admin.analytics.search.help.header', lang) + "\n"
            message += t('admin.analytics.search.help.body', lang) + "\n\n"
            message += t('admin.analytics.search.prompt', lang)
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]]
            await self._safe_edit_message(query, message, keyboard)
        # علامت‌گذاری برای حالت جستجو
        context.user_data['analytics_search_mode'] = True
        return ADMIN_MENU

    async def handle_search_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """دریافت متن جستجو و نمایش نتایج (ساده و امن)"""
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not update.message:
            return ADMIN_MENU
        if not context.user_data.get('analytics_search_mode'):
            return ADMIN_MENU
        q = (update.message.text or '').strip()
        if not q:
            await update.message.reply_text(t('admin.analytics.search.prompt', lang))
            return ADMIN_MENU
        try:
            # نمایش وضعیت جستجو
            await update.message.reply_text(t('admin.analytics.search.searching', lang, query=q))
            pattern = f"%{q.lower()}%"
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    WITH base AS (
                        SELECT a.id, a.name, a.code, w.name AS weapon, wc.name AS category
                        FROM attachments a
                        LEFT JOIN weapons w ON a.weapon_id = w.id
                        LEFT JOIN weapon_categories wc ON w.category_id = wc.id
                        WHERE LOWER(a.name) LIKE %s
                           OR CAST(a.code AS TEXT) LIKE %s
                           OR LOWER(w.name) LIKE %s
                    ),
                    agg AS (
                        SELECT m.attachment_id,
                               COUNT(CASE WHEN m.action_type='view' THEN 1 END) AS views,
                               COUNT(CASE WHEN m.action_type='click' THEN 1 END) AS clicks
                        FROM attachment_metrics m
                        WHERE m.attachment_id IN (SELECT id FROM base)
                        GROUP BY m.attachment_id
                    )
                    SELECT b.id AS att_id,
                           b.name AS attachment,
                           COALESCE(b.weapon,'Unknown') AS weapon,
                           COALESCE(b.category,'Unknown') AS category,
                           COALESCE(agg.views,0) AS views,
                           COALESCE(agg.clicks,0) AS clicks
                    FROM base b
                    LEFT JOIN agg ON agg.attachment_id = b.id
                    ORDER BY views DESC
                    LIMIT 10
                    """,
                    (pattern, pattern, pattern)
                )
                rows = cursor.fetchall() or []
            if not rows:
                await update.message.reply_text(
                    t('admin.analytics.search.no_results.title', lang) + "\n\n" + t('admin.analytics.search.no_results.tips', lang)
                )
                context.user_data.pop('analytics_search_mode', None)
                return ADMIN_MENU
            # ساخت پیام نتایج
            header = t('admin.analytics.search.results.header', lang, query=q)
            count = t('admin.analytics.search.results.count', lang, n=len(rows))
            lines = [header, count, ""]
            for r in rows:
                att = self._escape_markdown(r['attachment'])
                wpn = self._escape_markdown(r['weapon'])
                cat = self._escape_markdown(r['category'])
                views = f"{int(r['views']):,}"
                clicks = f"{int(r['clicks']):,}"
                lines.append(f"• *{att}*")
                lines.append(t('admin.analytics.search.lines.meta', lang, weapon=wpn, category=cat))
                lines.append(t('admin.analytics.search.lines.stats', lang, views=views, clicks=clicks))
                lines.append("")
            # کیبورد دکمه‌های جزئیات برای هر نتیجه
            keyboard = []
            for r in rows:
                try:
                    att_id = r['att_id']
                    title = f"ℹ {r['attachment']}"
                    keyboard.append([InlineKeyboardButton(title, callback_data=f"weapon_details_{att_id}")])
                except Exception:
                    continue
            await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        except Exception as e:
            logger.error(f"Error in handle_search_text: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await update.message.reply_text(
                t('admin.analytics.search.error.title', lang) + "\n\n" + t('admin.analytics.search.error.body', lang)
            )
        context.user_data.pop('analytics_search_mode', None)
        return ADMIN_MENU

    async def download_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """دانلود گزارش CSV 7 روز اخیر برای آمار اتچمنت‌ها"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not query:
            return ADMIN_MENU
        await query.answer()
        try:
            date7 = get_date_interval(7)
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 
                        a.name as attachment,
                        COALESCE(w.name,'Unknown') as weapon,
                        COALESCE(wc.name,'Unknown') as category,
                        COUNT(CASE WHEN m.action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN m.action_type='click' THEN 1 END) as clicks,
                        COUNT(DISTINCT m.user_id) as users
                    FROM attachment_metrics m
                    JOIN attachments a ON m.attachment_id = a.id
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    LEFT JOIN weapon_categories wc ON w.category_id = wc.id
                    WHERE CAST(m.action_date AS DATE) >= {date7}
                    GROUP BY a.id, a.name, w.name, wc.name
                    ORDER BY views DESC
                    LIMIT 200
                """)
                rows = cursor.fetchall() or []
            # ساخت CSV در حافظه
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Attachment','Weapon','Category','Views','Clicks','Users'])
            for r in rows:
                writer.writerow([
                    r['attachment'], r['weapon'], r['category'],
                    int(r['views'] or 0), int(r['clicks'] or 0), int(r['users'] or 0)
                ])
            data = io.BytesIO(output.getvalue().encode('utf-8'))
            output.close()
            filename = f"analytics_report_{datetime.now().strftime('%Y%m%d')}.csv"
            await query.message.reply_document(InputFile(data, filename=filename),
                                               caption=t('admin.analytics.weekly.title', lang))
        except Exception as e:
            logger.error(f"Error in download_report: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.answer(t('error.generic', lang), show_alert=True)
        return ADMIN_MENU

    async def daily_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمایش نمودار متنی ۷ روز اخیر (Views/Clicks)"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not query:
            return ADMIN_MENU
        await query.answer()
        try:
            date7 = get_date_interval(7)
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 
                        DATE(action_date) as date,
                        COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks
                    FROM attachment_metrics
                    WHERE CAST(action_date AS DATE) >= {date7}
                    GROUP BY DATE(action_date)
                    ORDER BY date ASC
                """)
                rows = cursor.fetchall() or []
            # تبدیل به دیکشنری برای پر کردن روزهای خالی
            from datetime import date as _date
            today = datetime.utcnow().date()
            days = [today - timedelta(days=i) for i in range(6, -1, -1)]
            data_map = {str(r['date']): {'views': int(r['views'] or 0), 'clicks': int(r['clicks'] or 0)} for r in rows}
            series = []
            max_views = 0
            for d in days:
                key = str(d)
                v = data_map.get(key, {'views': 0, 'clicks': 0})
                series.append((key, v['views'], v['clicks']))
                if v['views'] > max_views:
                    max_views = v['views']
            width = 28
            lines = [t('admin.analytics.weekly.title', lang), "", "```"]
            for key, views, clicks in series:
                bar_len = int((views / max_views) * width) if max_views > 0 else 0
                bar = '█' * bar_len
                lines.append(f"{key} | {bar:<{width}} {views:>5} / {clicks:>5}")
            lines.append("```")
            await query.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error in daily_chart: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.answer(t('error.generic', lang), show_alert=True)
        return ADMIN_MENU

    async def download_daily_csv(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """دانلود CSV تجمیعی روزانه برای ۷ روز اخیر"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not query:
            return ADMIN_MENU
        await query.answer()
        try:
            date7 = get_date_interval(7)
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT 
                        DATE(action_date) as date,
                        COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks,
                        COUNT(DISTINCT user_id) as users
                    FROM attachment_metrics
                    WHERE CAST(action_date AS DATE) >= {date7}
                    GROUP BY DATE(action_date)
                    ORDER BY date ASC
                """)
                rows = cursor.fetchall() or []
            # کامل‌سازی روزهای خالی و ساخت CSV
            today = datetime.utcnow().date()
            days = [today - timedelta(days=i) for i in range(6, -1, -1)]
            data_map = {str(r['date']): (int(r['views'] or 0), int(r['clicks'] or 0), int(r['users'] or 0)) for r in rows}
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Date','Views','Clicks','Users'])
            for d in days:
                v, c, u = data_map.get(str(d), (0,0,0))
                writer.writerow([str(d), v, c, u])
            data = io.BytesIO(output.getvalue().encode('utf-8'))
            output.close()
            filename = f"daily_breakdown_{datetime.now().strftime('%Y%m%d')}.csv"
            await query.message.reply_document(InputFile(data, filename=filename),
                                               caption=t('admin.analytics.weekly.title', lang))
        except Exception as e:
            logger.error(f"Error in download_daily_csv: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.answer(t('error.generic', lang), show_alert=True)
        return ADMIN_MENU

    async def weapon_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمایش جزئیات یک اتچمنت بر اساس شناسه در callback_data: weapon_details_<id>"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not query:
            return ADMIN_MENU
        await query.answer()
        data = query.data or ""
        att_id = None
        if data.startswith("weapon_details_"):
            try:
                att_id = int(data.split("_")[-1])
            except Exception:
                att_id = None
        if not att_id:
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]]
            await self._safe_edit_message(query, t('admin.analytics.weapon_stats.no_data.title', lang), keyboard)
            return ADMIN_MENU

        message = ""
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                # Meta
                cursor.execute(
                    """
                    SELECT a.name as attachment, a.code, a.mode,
                           COALESCE(w.name,'Unknown') as weapon,
                           COALESCE(wc.name,'Unknown') as category
                    FROM attachments a
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    LEFT JOIN weapon_categories wc ON w.category_id = wc.id
                    WHERE a.id = %s
                    """,
                    (att_id,)
                )
                meta = cursor.fetchone() or {}
                # 30d summary
                d30 = get_date_interval(30)
                cursor.execute(
                    f"""
                    SELECT 
                        COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks,
                        COUNT(DISTINCT user_id) as users
                    FROM attachment_metrics
                    WHERE attachment_id = %s AND CAST(action_date AS DATE) >= {d30}
                    """,
                    (att_id,)
                )
                s = cursor.fetchone() or {}
                views = int(s.get('views') or 0)
                clicks = int(s.get('clicks') or 0)
                users = int(s.get('users') or 0)
                rate = (float(clicks)/float(views)*100) if views > 0 else 0.0

                # 7d breakdown
                d7 = get_date_interval(7)
                cursor.execute(
                    f"""
                    SELECT DATE(action_date) as date,
                           COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                           COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks
                    FROM attachment_metrics
                    WHERE attachment_id = %s AND CAST(action_date AS DATE) >= {d7}
                    GROUP BY DATE(action_date)
                    ORDER BY date ASC
                    """,
                    (att_id,)
                )
                rows = cursor.fetchall() or []

            # Compose message
            safe_att = self._escape_markdown(meta.get('attachment') or 'Unknown')
            safe_weapon = self._escape_markdown(meta.get('weapon') or 'Unknown')
            code = meta.get('code') or '-'
            mode_val = meta.get('mode') or ''
            mode_title = t('admin.analytics.weapon_stats.buttons.br', lang) if mode_val == 'br' else t('admin.analytics.weapon_stats.buttons.mp', lang) if mode_val == 'mp' else t('admin.analytics.weapon_stats.buttons.all', lang)

            message += f"🔫 *{safe_att}*\n"
            message += t('admin.analytics.lines.weapon', lang, weapon=safe_weapon) + "\n"
            message += t('admin.analytics.lines.code', lang, code=code) + "\n"
            message += t('admin.analytics.weapon_stats.mode', lang, mode=mode_title) + "\n\n"

            message += t('admin.analytics.weekly.summary.header', lang) + "\n"
            message += t('admin.analytics.weekly.summary.views', lang, n=f"{views:,}") + "\n"
            message += t('admin.analytics.weekly.summary.clicks', lang, n=f"{clicks:,}") + "\n"
            message += t('admin.analytics.weekly.summary.users', lang, n=f"{users:,}") + "\n"
            message += t('admin.analytics.weekly.summary.engagement', lang, rate=f"{rate:.1f}") + "\n\n"

            # 7d ASCII chart
            today = datetime.utcnow().date()
            days = [today - timedelta(days=i) for i in range(6, -1, -1)]
            data_map = {str(r['date']): (int(r['views'] or 0), int(r['clicks'] or 0)) for r in rows}
            max_views = max([v for (v, _) in data_map.values()], default=0)
            width = 24
            chart_lines = ["```"]
            for d in days:
                v, c = data_map.get(str(d), (0,0))
                bar_len = int((v / max_views) * width) if max_views > 0 else 0
                bar = '█' * bar_len
                chart_lines.append(f"{str(d)} | {bar:<{width}} {v:>5} / {c:>5}")
            chart_lines.append("```")
            message += "\n".join(chart_lines)
        except Exception as e:
            logger.error(f"Error in weapon_details: {e}")
            import traceback
            logger.error(traceback.format_exc())
            message = t('error.generic', lang)

        keyboard = [
            [InlineKeyboardButton(t('admin.analytics.buttons.daily_chart', lang), callback_data=f"att_daily_chart_{att_id}")],
            [InlineKeyboardButton(t('admin.analytics.buttons.download_csv', lang), callback_data=f"att_download_csv_{att_id}")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]
        ]
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU

    async def att_daily_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمودار متنی ۷ روز اخیر برای یک اتچمنت خاص: att_daily_chart_<id>"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not query:
            return ADMIN_MENU
        await query.answer()
        data = query.data or ""
        att_id = None
        if data.startswith("att_daily_chart_"):
            try:
                att_id = int(data.split("_")[-1])
            except Exception:
                att_id = None
        if not att_id:
            await query.answer(t('error.generic', lang), show_alert=True)
            return ADMIN_MENU
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                # Get attachment name
                cursor.execute("SELECT name FROM attachments WHERE id = %s", (att_id,))
                row = cursor.fetchone() or {}
                att_name = self._escape_markdown(row.get('name') or 'Unknown')
                # 7d breakdown
                date7 = get_date_interval(7)
                cursor.execute(
                    f"""
                    SELECT DATE(action_date) as date,
                           COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                           COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks
                    FROM attachment_metrics
                    WHERE attachment_id = %s AND CAST(action_date AS DATE) >= {date7}
                    GROUP BY DATE(action_date)
                    ORDER BY date ASC
                    """,
                    (att_id,)
                )
                rows = cursor.fetchall() or []
            today = datetime.utcnow().date()
            days = [today - timedelta(days=i) for i in range(6, -1, -1)]
            data_map = {str(r['date']): (int(r['views'] or 0), int(r['clicks'] or 0)) for r in rows}
            max_views = max([v for (v, _) in data_map.values()], default=0)
            width = 28
            lines = [t('admin.analytics.daily.title', lang) + f" — *{att_name}*", "", "```"]
            for d in days:
                v, c = data_map.get(str(d), (0,0))
                bar_len = int((v / max_views) * width) if max_views > 0 else 0
                bar = '█' * bar_len
                lines.append(f"{str(d)} | {bar:<{width}} {v:>5} / {c:>5}")
            lines.append("```")
            await query.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error in att_daily_chart: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.answer(t('error.generic', lang), show_alert=True)
        return ADMIN_MENU

    async def att_download_csv(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """دانلود CSV روزانه ۷ روز اخیر برای یک اتچمنت خاص: att_download_csv_<id>"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        if not query:
            return ADMIN_MENU
        await query.answer()
        data = query.data or ""
        att_id = None
        if data.startswith("att_download_csv_"):
            try:
                att_id = int(data.split("_")[-1])
            except Exception:
                att_id = None
        if not att_id:
            await query.answer(t('error.generic', lang), show_alert=True)
            return ADMIN_MENU
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                date7 = get_date_interval(7)
                cursor.execute(
                    f"""
                    SELECT DATE(action_date) as date,
                           COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                           COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks,
                           COUNT(DISTINCT user_id) as users
                    FROM attachment_metrics
                    WHERE attachment_id = %s AND CAST(action_date AS DATE) >= {date7}
                    GROUP BY DATE(action_date)
                    ORDER BY date ASC
                    """,
                    (att_id,)
                )
                rows = cursor.fetchall() or []
            from datetime import date as _date
            today = datetime.utcnow().date()
            days = [today - timedelta(days=i) for i in range(6, -1, -1)]
            data_map = {str(r['date']): (int(r['views'] or 0), int(r['clicks'] or 0), int(r['users'] or 0)) for r in rows}
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Date','Views','Clicks','Users'])
            for d in days:
                v, c, u = data_map.get(str(d), (0,0,0))
                writer.writerow([str(d), v, c, u])
            data_buf = io.BytesIO(output.getvalue().encode('utf-8'))
            output.close()
            filename = f"attachment_{att_id}_daily_{datetime.now().strftime('%Y%m%d')}.csv"
            await query.message.reply_document(InputFile(data_buf, filename=filename),
                                               caption=t('admin.analytics.daily.title', lang))
        except Exception as e:
            logger.error(f"Error in att_download_csv: {e}")
            import traceback
            logger.error(traceback.format_exc())
            await query.answer(t('error.generic', lang), show_alert=True)
        return ADMIN_MENU
    
    async def view_user_behavior(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """آنالیز رفتار کاربران (خلاصه + هایلایت‌ها)"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.analytics.user.loading', lang))
        
        message = t('admin.analytics.user.title', lang) + "\n\n"
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                date7 = get_date_interval(7)
                # Summary (7d)
                cursor.execute(f"""
                    SELECT 
                        COUNT(DISTINCT user_id) as active_users,
                        COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks
                    FROM attachment_metrics
                    WHERE CAST(action_date AS DATE) >= {date7}
                """)
                s = cursor.fetchone() or {}
                active_users = int(s.get('active_users') or 0)
                views = int(s.get('views') or 0)
                clicks = int(s.get('clicks') or 0)

                # Total users overall (all-time seen in metrics)
                cursor.execute("""
                    SELECT COUNT(DISTINCT user_id) as total_users
                    FROM attachment_metrics
                """)
                tu = cursor.fetchone() or {}
                total_users = int(tu.get('total_users') or 0)

                avg_views = (float(views)/float(active_users)) if active_users > 0 else 0.0
                engagement_rate = (float(clicks)/float(views)*100) if views > 0 else 0.0

                # Summary lines
                message += t('admin.analytics.user.summary.header', lang) + "\n"
                message += t('admin.analytics.user.summary.total_users', lang, n=f"{total_users:,}") + "\n"
                message += t('admin.analytics.user.summary.active_7d', lang, n=f"{active_users:,}") + "\n"
                message += t('admin.analytics.user.summary.avg_views', lang, n=f"{avg_views:.1f}") + "\n"
                message += t('admin.analytics.user.summary.engagement', lang, rate=f"{engagement_rate:.1f}") + "\n\n"

                # Per-user stats (7d)
                cursor.execute(f"""
                    SELECT 
                        user_id,
                        COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks,
                        COUNT(DISTINCT attachment_id) as atts,
                        MAX(action_date) as last_active
                    FROM attachment_metrics
                    WHERE CAST(action_date AS DATE) >= {date7}
                    GROUP BY user_id
                    ORDER BY views DESC
                """)
                rows = cursor.fetchall() or []

                # Optional ratings by user
                ratings = {}
                try:
                    cursor.execute("""
                        SELECT user_id, AVG(rating) as rating
                        FROM user_attachment_engagement
                        WHERE rating IS NOT NULL
                        GROUP BY user_id
                    """)
                    for r in cursor.fetchall() or []:
                        ratings[int(r['user_id'])] = float(r['rating'])
                except Exception:
                    pass

                very_active = []
                active = []
                moderate = []
                for r in rows:
                    v = int(r['views'] or 0)
                    c = int(r['clicks'] or 0)
                    a = int(r['atts'] or 0)
                    eng = (float(c)/float(v)*100) if v > 0 else 0.0
                    uid = int(r['user_id'])
                    last = str(r['last_active']) if r['last_active'] else None
                    data = {
                        'user_id': uid,
                        'views': v,
                        'clicks': c,
                        'atts': a,
                        'eng': eng,
                        'rating': ratings.get(uid),
                        'last': last
                    }
                    if v >= 50 or c >= 10:
                        very_active.append(data)
                    elif v >= 10 or c >= 3:
                        active.append(data)
                    else:
                        moderate.append(data)

                if rows:
                    # Very active block
                    if very_active:
                        message += t('admin.analytics.user.group.very_active.header', lang) + "\n"
                        for item in very_active[:3]:
                            name = self._escape_markdown(f"#{item['user_id']}")
                            message += f"\n🥇 *{name}*\n"
                            message += t('admin.analytics.user.line.views', lang, n=f"{item['views']:,}") + "\n"
                            message += t('admin.analytics.user.line.clicks', lang, n=f"{item['clicks']:,}") + "\n"
                            message += t('admin.analytics.user.line.attachments', lang, n=item['atts']) + "\n"
                            message += t('admin.analytics.user.line.engagement', lang, rate=f"{item['eng']:.0f}") + "\n"
                            if item.get('rating') is not None:
                                message += t('admin.analytics.user.line.rating', lang, rating=f"{item['rating']:.1f}") + "\n"
                            last_label = item['last'][:10] if item['last'] else t('common.unknown', lang)
                            message += t('admin.analytics.user.line.last', lang, time=last_label) + "\n"
                        message += "\n"

                    # Active block
                    if active:
                        message += t('admin.analytics.user.group.active.header', lang) + "\n"
                        for item in active[:2]:
                            name = self._escape_markdown(f"#{item['user_id']}")
                            message += t('admin.analytics.user.line.item', lang, name=name, views=f"{item['views']:,}", atts=item['atts']) + "\n"
                        message += "\n"

                    if moderate:
                        message += t('admin.analytics.user.group.moderate.count', lang, n=len(moderate)) + "\n"
                else:
                    message += t('admin.analytics.user.no_data.title', lang) + "\n\n" + t('admin.analytics.user.no_data.body', lang)
        except Exception as e:
            logger.error(f"Error in view_user_behavior: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            message = t('admin.analytics.user.error.title', lang) + "\n\n" + t('admin.analytics.user.error.body', lang)

        keyboard = [
            [InlineKeyboardButton(t('admin.analytics.buttons.more_details', lang), callback_data="user_behavior_details")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]
        ]
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU

    async def user_behavior_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """جزئیات رفتار کاربران (توزیع و برترین‌ها)"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer()

        message = t('admin.analytics.user_details.title', lang) + "\n\n"
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                date7 = get_date_interval(7)

                # Per-user stats for distribution
                cursor.execute(f"""
                    SELECT 
                        user_id,
                        COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks
                    FROM attachment_metrics
                    WHERE CAST(action_date AS DATE) >= {date7}
                    GROUP BY user_id
                """)
                rows = cursor.fetchall() or []

                very = 0
                act = 0
                mod = 0
                for r in rows:
                    v = int(r['views'] or 0)
                    c = int(r['clicks'] or 0)
                    if v >= 50 or c >= 10:
                        very += 1
                    elif v >= 10 or c >= 3:
                        act += 1
                    else:
                        mod += 1

                total = very + act + mod
                if total > 0:
                    message += t('admin.analytics.user_details.dist.header', lang) + "\n"
                    def pct(x):
                        return f"{(x*100.0/total):.0f}"
                    message += t('admin.analytics.user_details.dist.line', lang, icon='🔥', cat=t('admin.analytics.user_details.dist.cat.very_active', lang), count=very, pct=pct(very)) + "\n"
                    message += t('admin.analytics.user_details.dist.line', lang, icon='⚡', cat=t('admin.analytics.user_details.dist.cat.active', lang), count=act, pct=pct(act)) + "\n"
                    message += t('admin.analytics.user_details.dist.line', lang, icon='📊', cat=t('admin.analytics.user_details.dist.cat.moderate', lang), count=mod, pct=pct(mod)) + "\n\n"

                # Top attachments by distinct users (7d)
                cursor.execute(f"""
                    SELECT a.name, COUNT(DISTINCT m.user_id) as users
                    FROM attachment_metrics m
                    JOIN attachments a ON m.attachment_id = a.id
                    WHERE m.action_type='view' AND CAST(m.action_date AS DATE) >= {date7}
                    GROUP BY a.id, a.name
                    ORDER BY users DESC
                    LIMIT 3
                """)
                top = cursor.fetchall() or []
                if top:
                    message += t('admin.analytics.user_details.top.header', lang) + "\n"
                    for i,row in enumerate(top,1):
                        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉"
                        safe_name = self._escape_markdown(row['name'])
                        # Minimal line without extra text to avoid missing keys
                        message += f"{medal} {safe_name} — {int(row['users'])}\n"
                    message += "\n"

                # Weekly active users
                cursor.execute(f"""
                    SELECT COUNT(DISTINCT user_id) as users
                    FROM attachment_metrics
                    WHERE CAST(action_date AS DATE) >= {date7}
                """)
                w = cursor.fetchone() or {}
                weekly = int(w.get('users') or 0)
                if weekly > 0:
                    message += t('admin.analytics.user_details.weekly', lang, n=weekly) + "\n"
        except Exception as e:
            logger.error(f"Error in user_behavior_details: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            message = t('admin.analytics.user.error.title', lang) + "\n\n" + t('admin.analytics.user.error.body', lang)

        keyboard = [
            [
                InlineKeyboardButton(t('admin.analytics.buttons.daily_chart', lang), callback_data="daily_chart"),
                InlineKeyboardButton(t('admin.analytics.buttons.download_csv', lang), callback_data="download_daily_csv")
            ],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]
        ]
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU
    
    async def ws_back_to_categories(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """بازگشت به فهرست دسته‌ها برای مود انتخاب‌شده"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer()
        
        # بازیابی مود انتخاب‌شده
        data = context.user_data.get('ws_mode', 'ws_mode_all')
        mode_map = {
            'ws_mode_br': t('admin.analytics.weapon_stats.buttons.br', lang),
            'ws_mode_mp': t('admin.analytics.weapon_stats.buttons.mp', lang),
            'ws_mode_all': t('admin.analytics.weapon_stats.buttons.all', lang),
        }
        mode_title = mode_map.get(data, '')
        
        message = t('admin.analytics.weapon_stats.title', lang) + "\n"
        message += t('admin.analytics.weapon_stats.mode', lang, mode=mode_title) + "\n\n"
        message += t('admin.analytics.weapon_stats.choose_category', lang)
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name
                    FROM weapon_categories
                    ORDER BY name
                """)
                cats = cursor.fetchall()
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            message = t('admin.analytics.weapon_stats.error.categories', lang)
            cats = []
        
        keyboard = []
        row = []
        for c in cats or []:
            # map DB category name to English+emoji label from WEAPON_CATEGORIES when possible
            _db_name = (c.get('name') or '').strip()
            title_src = self._map_category_name_to_label(_db_name)
            title = self._escape_markdown(title_src)
            row.append(InlineKeyboardButton(title, callback_data=f"weapon_stats_cat_{c['id']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton(t('admin.analytics.buttons.back_to_mode_selection', lang), callback_data="ws_back_to_mode")])
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")])
        
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU
    
    async def view_weapon_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمایش انتخاب مود برای آمار سلاح‌ها"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer()
        
        message = t('admin.analytics.weapon_stats.title', lang) + "\n\n"
        message += t('admin.analytics.weapon_stats.choose_mode', lang)
        
        keyboard = [
            [
                InlineKeyboardButton(t('admin.analytics.weapon_stats.buttons.br', lang), callback_data="weapon_stats_mode_br"),
                InlineKeyboardButton(t('admin.analytics.weapon_stats.buttons.mp', lang), callback_data="weapon_stats_mode_mp")
            ],
            [InlineKeyboardButton(t('admin.analytics.weapon_stats.buttons.all', lang), callback_data="weapon_stats_mode_all")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]
        ]
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU

    async def ws_choose_mode(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """پس از انتخاب مود، نمایش لیست دسته‌های سلاح"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        data = query.data
        if data.startswith('weapon_stats_mode_'):
            suffix = data.replace('weapon_stats_mode_', '')
            data = f"ws_mode_{suffix}"
        await query.answer()
        
        mode_map = {
            'ws_mode_br': t('admin.analytics.weapon_stats.buttons.br', lang),
            'ws_mode_mp': t('admin.analytics.weapon_stats.buttons.mp', lang),
            'ws_mode_all': t('admin.analytics.weapon_stats.buttons.all', lang),
        }
        context.user_data['ws_mode'] = data
        mode_title = mode_map.get(data, '')
        
        message = t('admin.analytics.weapon_stats.title', lang) + "\n"
        message += t('admin.analytics.weapon_stats.mode', lang, mode=mode_title) + "\n\n"
        message += t('admin.analytics.weapon_stats.choose_category', lang)
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, name
                    FROM weapon_categories
                    ORDER BY name
                """)
                cats = cursor.fetchall()
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            message = t('admin.analytics.weapon_stats.error.categories', lang)
            cats = []
        
        keyboard = []
        row = []
        for c in cats or []:
            # map DB category name to English+emoji label from WEAPON_CATEGORIES when possible
            _db_name = (c.get('name') or '').strip()
            title_src = self._map_category_name_to_label(_db_name)
            title = self._escape_markdown(title_src)
            row.append(InlineKeyboardButton(title, callback_data=f"weapon_stats_cat_{c['id']}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton(t('admin.analytics.buttons.back_to_mode_selection', lang), callback_data="ws_back_to_mode")])
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")])
        
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU

    async def ws_choose_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمایش آمار کلی برای دسته انتخاب‌شده"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer()
        
        # Handle both new and legacy prefixes
        data = query.data
        if 'weapon_stats_cat_' in data:
            cat_id = int(data.replace('weapon_stats_cat_', ''))
        else:
            cat_id = int(data.replace('ws_cat_', ''))
            
        mode_key = context.user_data.get('ws_mode', 'ws_mode_all')
        mode_map = {
            'ws_mode_br': t('admin.analytics.weapon_stats.buttons.br', lang),
            'ws_mode_mp': t('admin.analytics.weapon_stats.buttons.mp', lang),
            'ws_mode_all': t('admin.analytics.weapon_stats.buttons.all', lang),
        }
        mode_title = mode_map.get(mode_key, '')
        
        # Aggregate stats for attachments in this category
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                # اعمال فیلتر مود در صورت انتخاب BR/MP
                mode_value = None
                if mode_key == 'ws_mode_br':
                    mode_value = 'br'
                elif mode_key == 'ws_mode_mp':
                    mode_value = 'mp'
                # ساخت آمار از جدول metrics
                if mode_value:
                    cursor.execute("""
                        WITH base AS (
                            SELECT a.id
                            FROM attachments a
                            JOIN weapons w ON a.weapon_id = w.id
                            JOIN weapon_categories wc ON w.category_id = wc.id
                            WHERE wc.id = %s AND a.mode = %s
                        ),
                        views AS (
                            SELECT m.attachment_id, COUNT(*) FILTER (WHERE m.action_type='view') AS v
                            FROM attachment_metrics m
                            WHERE m.attachment_id IN (SELECT id FROM base)
                            GROUP BY m.attachment_id
                        )
                        SELECT 
                            (SELECT name FROM weapon_categories WHERE id = %s) AS category,
                            (SELECT COUNT(*) FROM base) AS att_count,
                            COALESCE((SELECT SUM(v) FROM views),0) AS views_sum,
                            COALESCE((SELECT AVG(v) FROM views),0) AS views_avg,
                            COALESCE((SELECT MAX(v) FROM views),0) AS views_max
                    """, (cat_id, mode_value, cat_id))
                else:
                    cursor.execute("""
                        WITH base AS (
                            SELECT a.id
                            FROM attachments a
                            JOIN weapons w ON a.weapon_id = w.id
                            JOIN weapon_categories wc ON w.category_id = wc.id
                            WHERE wc.id = %s
                        ),
                        views AS (
                            SELECT m.attachment_id, COUNT(*) FILTER (WHERE m.action_type='view') AS v
                            FROM attachment_metrics m
                            WHERE m.attachment_id IN (SELECT id FROM base)
                            GROUP BY m.attachment_id
                        )
                        SELECT 
                            (SELECT name FROM weapon_categories WHERE id = %s) AS category,
                            (SELECT COUNT(*) FROM base) AS att_count,
                            COALESCE((SELECT SUM(v) FROM views),0) AS views_sum,
                            COALESCE((SELECT AVG(v) FROM views),0) AS views_avg,
                            COALESCE((SELECT MAX(v) FROM views),0) AS views_max
                    """, (cat_id, cat_id))
                agg = cursor.fetchone()
        except Exception as e:
            logger.error(f"Error loading weapon stats: {e}")
            agg = None
        
        if agg:
            category_name = self._escape_markdown(agg['category'])
            message = t('admin.analytics.weapon_stats.title', lang) + "\n"
            message += t('admin.analytics.weapon_stats.mode', lang, mode=mode_title) + "\n\n"
            message += f"📂 {category_name}\n\n"
            message += t('admin.analytics.weapon_stats.lines.attach_count', lang, n=agg['att_count']) + "\n"
            message += t('admin.analytics.weapon_stats.lines.views', lang, views=f"{int(agg['views_sum']):,}") + "\n"
            message += t('admin.analytics.weapon_stats.lines.avg_max', lang, avg=f"{float(agg['views_avg']):.1f}", max=f"{int(agg['views_max']):,}") + "\n"
        else:
            message = t('admin.analytics.weapon_stats.no_data.title', lang) + "\n" + t('admin.analytics.weapon_stats.no_data.suggestion', lang)
        
        keyboard = [
            [InlineKeyboardButton(t('admin.analytics.buttons.change_category', lang), callback_data="ws_back_to_categories")],
            [InlineKeyboardButton(t('admin.analytics.buttons.back_to_mode_selection', lang), callback_data="ws_back_to_mode")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]
        ]
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU
    
    async def refresh_trending(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Refresh trending by delegating to view_trending"""
        return await self.view_trending(update, context)
    
    async def view_underperforming(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """نمایش آیتم‌های کم‌عملکرد بر اساس بازدید و نرخ تعامل"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.analytics.loading_under', lang))
        
        message = t('admin.analytics.under.title', lang) + "\n"
        message += t('admin.analytics.under.subtitle', lang) + "\n\n"
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    WITH agg AS (
                        SELECT attachment_id,
                               COUNT(CASE WHEN action_type='view' THEN 1 END) AS views,
                               COUNT(CASE WHEN action_type='click' THEN 1 END) AS clicks
                        FROM attachment_metrics
                        GROUP BY attachment_id
                    )
                    SELECT 
                        a.id,
                        a.name,
                        COALESCE(w.name, 'Unknown') as weapon,
                        COALESCE(agg.views,0) AS views,
                        COALESCE(agg.clicks,0) AS clicks
                    FROM attachments a
                    LEFT JOIN agg ON agg.attachment_id = a.id
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    WHERE COALESCE(agg.views,0) < 20
                       OR (CAST(COALESCE(agg.clicks,0) AS FLOAT) / NULLIF(COALESCE(agg.views,0), 0)) * 100 < 5
                    ORDER BY COALESCE(agg.views,0) ASC
                    LIMIT 20
                """)
                items = cursor.fetchall()
            
            if items:
                count = 0
                for it in items:
                    name = it['name']
                    weapon = it['weapon']
                    views = it['views'] or 0
                    clicks = it['clicks'] or 0
                    rate = (float(clicks) / float(views) * 100) if views > 0 else 0.0
                    
                    issues = []
                    if views < 20:
                        issues.append(t('admin.analytics.issue.low_views', lang))
                    if rate < 5.0:
                        issues.append(t('admin.analytics.issue.low_engagement', lang))
                    
                    safe_name = self._escape_markdown(name)
                    safe_weapon = self._escape_markdown(weapon)
                    
                    message += f"• *{safe_name}*\n"
                    if issues:
                        message += "   " + " • ".join(issues) + "\n"
                    message += t('admin.analytics.lines.weapon', lang, weapon=safe_weapon) + "\n"
                    message += t('admin.analytics.search.lines.stats', lang, views=f"{views:,}", clicks=f"{clicks:,}") + "\n\n"
                    count += 1
                message += t('admin.analytics.under.total', lang, n=count) + "\n"
            else:
                message += t('admin.analytics.under.all_good', lang) + "\n"
        except Exception as e:
            logger.error(f"Error in view_underperforming: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            message = t('admin.analytics.under.title', lang) + "\n\n" + t('admin.analytics.daily.error.body', lang)
        finally:
            pass

        keyboard = []
        if items:
            added = 0
            for it in items:
                try:
                    att_id = it['id']
                    title = f"ℹ {it['name']}"
                    keyboard.append([InlineKeyboardButton(title, callback_data=f"weapon_details_{att_id}")])
                    added += 1
                    if added >= 10:
                        break
                except Exception:
                    continue
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")])
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU

    async def daily_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """گزارش روزانه ساده بر اساس آمار امروز"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.analytics.loading', lang))
        
        message = t('admin.analytics.daily.title', lang) + "\n\n"
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                today = get_current_date()
                # Summary
                cursor.execute(f"""
                    SELECT 
                        COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks,
                        COUNT(DISTINCT user_id) as users
                    FROM attachment_metrics
                    WHERE CAST(action_date AS DATE) = {today}
                """)
                s = cursor.fetchone()
                views = s['views'] if s else 0
                clicks = s['clicks'] if s else 0
                users = s['users'] if s else 0
                rate = (float(clicks)/float(views)*100) if views > 0 else 0.0
                
                message += t('admin.analytics.daily.stats.header', lang) + "\n"
                message += t('admin.analytics.daily.stats.views', lang, n=views) + "\n"
                message += t('admin.analytics.daily.stats.clicks', lang, n=clicks) + "\n"
                message += t('admin.analytics.daily.stats.users', lang, n=users) + "\n"
                message += t('admin.analytics.daily.stats.engagement', lang, rate=f"{rate:.1f}") + "\n\n"
                
                # Top today
                cursor.execute(f"""
                    SELECT a.name, COALESCE(w.name,'Unknown') as weapon, COUNT(*) as v
                    FROM attachment_metrics m
                    JOIN attachments a ON m.attachment_id = a.id
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    WHERE m.action_type='view' AND CAST(m.action_date AS DATE) = {today}
                    GROUP BY a.id, a.name, w.name
                    ORDER BY v DESC
                    LIMIT 3
                """)
                top = cursor.fetchall()
                if top:
                    message += t('admin.analytics.daily.top.header', lang) + "\n"
                    for i,row in enumerate(top,1):
                        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉"
                        safe_name = self._escape_markdown(row['name'])
                        safe_weapon = self._escape_markdown(row['weapon'])
                        message += f"{medal} *{safe_name}*\n"
                        message += t('admin.analytics.lines.weapon', lang, weapon=safe_weapon) + "\n"
                        message += t('admin.analytics.fallback.lines.views', lang, value=f"{row['v']:,}") + "\n\n"
                else:
                    message += t('admin.analytics.daily.no_data.title', lang) + "\n\n" + t('admin.analytics.daily.no_data.body', lang)
        except Exception as e:
            logger.error(f"Error in daily_report: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            message = t('admin.analytics.daily.error.title', lang) + "\n\n" + t('admin.analytics.daily.error.body', lang)
        finally:
            pass
        
        keyboard = [
            [
                InlineKeyboardButton(t('admin.analytics.buttons.daily_chart', lang), callback_data="daily_chart"),
                InlineKeyboardButton(t('admin.analytics.buttons.download_csv', lang), callback_data="download_daily_csv")
            ],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]
        ]
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU

    async def weekly_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """گزارش هفتگی ساده بر اساس آمار ۷ روز اخیر"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.analytics.loading', lang))
        
        message = t('admin.analytics.weekly.title', lang) + "\n\n"
        
        try:
            with self._get_db_connection() as conn:
                cursor = conn.cursor()
                date7 = get_date_interval(7)
                cursor.execute(f"""
                    SELECT 
                        COUNT(CASE WHEN action_type='view' THEN 1 END) as views,
                        COUNT(CASE WHEN action_type='click' THEN 1 END) as clicks,
                        COUNT(DISTINCT user_id) as users
                    FROM attachment_metrics
                    WHERE CAST(action_date AS DATE) >= {date7}
                """)
                s = cursor.fetchone()
                views = s['views'] if s else 0
                clicks = s['clicks'] if s else 0
                users = s['users'] if s else 0
                rate = (float(clicks)/float(views)*100) if views > 0 else 0.0
                
                message += t('admin.analytics.weekly.summary.header', lang) + "\n"
                message += t('admin.analytics.weekly.summary.views', lang, n=views) + "\n"
                message += t('admin.analytics.weekly.summary.clicks', lang, n=clicks) + "\n"
                message += t('admin.analytics.weekly.summary.users', lang, n=users) + "\n"
                message += t('admin.analytics.weekly.summary.engagement', lang, rate=f"{rate:.1f}") + "\n\n"
                
                cursor.execute(f"""
                    SELECT a.name, COALESCE(w.name,'Unknown') as weapon, COUNT(*) as v
                    FROM attachment_metrics m
                    JOIN attachments a ON m.attachment_id = a.id
                    LEFT JOIN weapons w ON a.weapon_id = w.id
                    WHERE m.action_type='view' AND CAST(m.action_date AS DATE) >= {date7}
                    GROUP BY a.id, a.name, w.name
                    ORDER BY v DESC
                    LIMIT 3
                """)
                top = cursor.fetchall()
                if top:
                    message += t('admin.analytics.weekly.top.header', lang) + "\n"
                    for i,row in enumerate(top,1):
                        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉"
                        safe_name = self._escape_markdown(row['name'])
                        safe_weapon = self._escape_markdown(row['weapon'])
                        message += f"{medal} *{safe_name}*\n"
                        message += t('admin.analytics.lines.weapon_simple', lang, weapon=safe_weapon) + "\n"
                        message += t('admin.analytics.fallback.lines.views', lang, value=f"{row['v']:,}") + "\n\n"
                else:
                    message += t('admin.analytics.weekly.no_data.title', lang) + "\n\n" + t('admin.analytics.weekly.no_data.body', lang)
        except Exception as e:
            logger.error(f"Error in weekly_report: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            message = t('admin.analytics.weekly.error.title', lang) + "\n\n" + t('admin.analytics.weekly.error.body', lang)
        finally:
            pass
        
        keyboard = [
            [
                InlineKeyboardButton(t('admin.analytics.buttons.daily_chart', lang), callback_data="daily_chart"),
                InlineKeyboardButton(t('admin.analytics.buttons.download_csv', lang), callback_data="download_daily_csv")
            ],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="analytics_menu")]
        ]
        await self._safe_edit_message(query, message, keyboard)
        return ADMIN_MENU
    
    def get_conversation_handler(self) -> ConversationHandler:
        """Get conversation handler for analytics dashboard"""
        return ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.analytics_menu, pattern="^analytics_menu$"),
                CallbackQueryHandler(self.analytics_menu, pattern="^attachment_analytics$")
            ],
            states={
                ANALYTICS_MENU: [
                    # Legacy callbacks
                    CallbackQueryHandler(self.view_trending, pattern="^view_trending$"),
                    CallbackQueryHandler(self.view_underperforming, pattern="^view_underperforming$"),
                    CallbackQueryHandler(self.view_weapon_stats, pattern="^view_weapon_stats$"),
                    CallbackQueryHandler(self.view_user_behavior, pattern="^view_user_behavior$"),
                    CallbackQueryHandler(self.daily_report, pattern="^daily_report$"),
                    CallbackQueryHandler(self.weekly_report, pattern="^weekly_report$"),
                    # New analytics_* callbacks to match registry
                    CallbackQueryHandler(self.view_trending, pattern="^analytics_view_trending$"),
                    CallbackQueryHandler(self.view_underperforming, pattern="^analytics_view_underperforming$"),
                    CallbackQueryHandler(self.view_weapon_stats, pattern="^analytics_view_weapon_stats$"),
                    CallbackQueryHandler(self.view_user_behavior, pattern="^analytics_view_user_behavior$"),
                    CallbackQueryHandler(self.daily_report, pattern="^analytics_daily_report$"),
                    CallbackQueryHandler(self.weekly_report, pattern="^analytics_weekly_report$"),
                    # Common
                    CallbackQueryHandler(self.daily_chart, pattern="^daily_chart$"),
                    CallbackQueryHandler(self.download_daily_csv, pattern="^download_daily_csv$"),
                    CallbackQueryHandler(self.att_daily_chart, pattern="^att_daily_chart_\\d+$"),
                    CallbackQueryHandler(self.att_download_csv, pattern="^att_download_csv_\\d+$"),
                    CallbackQueryHandler(self.search_attachment_stats, pattern="^analytics_search_attachment$"),
                    CallbackQueryHandler(self.download_report, pattern="^analytics_download_report$"),
                    CallbackQueryHandler(self.weapon_details, pattern="^weapon_details_\\d+$"),
                    CallbackQueryHandler(self.ws_choose_mode, pattern="^ws_mode_(br|mp|all)$"),
                    CallbackQueryHandler(self.view_weapon_stats, pattern="^ws_back_to_mode$"),
                    CallbackQueryHandler(self.ws_choose_category, pattern="^ws_cat_\\d+$"),
                    CallbackQueryHandler(self.ws_choose_category, pattern="^weapon_stats_cat_\\d+$"),
                    CallbackQueryHandler(self.ws_back_to_categories, pattern="^ws_back_to_categories$"),
                    CallbackQueryHandler(self.user_behavior_details, pattern="^user_behavior_details$"),
                    CallbackQueryHandler(self.analytics_menu, pattern="^analytics_menu$"),
                    CallbackQueryHandler(self.admin_cancel, pattern="^admin_menu_return$")
                ],
                VIEW_TRENDING: [
                    CallbackQueryHandler(self.refresh_trending, pattern="^refresh_trending$"),
                    CallbackQueryHandler(self.analytics_menu, pattern="^analytics_menu$")
                ],
                VIEW_UNDERPERFORMING: [
                    CallbackQueryHandler(self.analytics_menu, pattern="^analytics_menu$")
                ],
                VIEW_WEAPON_STATS: [
                    CallbackQueryHandler(self.analytics_menu, pattern="^analytics_menu$")
                ],
                SEARCH_ATTACH: [
                    MessageHandler(filters.TEXT & (~filters.COMMAND), self.handle_search_text),
                    CallbackQueryHandler(self.analytics_menu, pattern="^analytics_menu$")
                ]
            },
            fallbacks=[
                CallbackQueryHandler(self.admin_cancel, pattern="^admin_cancel$"),
                MessageHandler(filters.Regex("^/cancel$"), self.admin_cancel)
            ]
        )






