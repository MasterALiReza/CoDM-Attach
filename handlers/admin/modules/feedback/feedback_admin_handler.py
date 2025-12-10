"""
Admin Feedback Dashboard - مدیریت و گزارش‌های بازخورد اتچمنت‌ها

✨ Updated: 2025-01-17
- Added sql_helpers for cross-database date queries
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config.config import CATEGORIES, WEAPON_CATEGORIES, GAME_MODES
from utils.logger import log_user_action, get_logger
from utils.i18n import t
from utils.language import get_user_lang
from handlers.admin.modules.base_handler import BaseAdminHandler
from datetime import datetime, timedelta
from core.database.sql_helpers import get_date_interval, get_datetime_interval
import io
import urllib.parse

logger = get_logger('admin', 'admin.log')


class FeedbackAdminHandler(BaseAdminHandler):
    """مدیریت گزارش‌های بازخورد برای ادمین‌ها"""
    
    @log_user_action("feedback_dashboard")
    async def show_feedback_dashboard(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی اصلی داشبورد بازخورد"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # وضعیت فیلتر فقط پیشنهادی‌ها
        suggested_only = context.user_data.get('fb_suggested_only', False)
        
        # دریافت آمار کلی (با درنظر گرفتن فیلتر پیشنهادی‌ها در صورت فعال بودن)
        stats = self._get_global_stats(suggested_only=suggested_only)
        
        text = (
            t('admin.feedback.dashboard.title', lang) + "\n\n" +
            t('admin.feedback.dashboard.overview.header', lang) + "\n" +
            t('admin.feedback.dashboard.overview.votes', lang, n=stats['total_votes']) + "\n" +
            t('admin.feedback.dashboard.overview.likes', lang, n=stats['total_likes']) + "\n" +
            t('admin.feedback.dashboard.overview.dislikes', lang, n=stats['total_dislikes']) + "\n" +
            t('admin.feedback.dashboard.overview.views', lang, n=stats['total_views']) + "\n" +
            t('admin.feedback.dashboard.overview.feedbacks', lang, n=stats['total_feedbacks']) + "\n" +
            t('admin.feedback.dashboard.overview.active_users', lang, n=stats['active_users']) + "\n\n" +
            t('admin.feedback.dashboard.period.label', lang, days=30) + "\n\n" +
            t('admin.feedback.dashboard.choose_report', lang)
        )
        
        status_word = t('common.enabled_word', lang) if suggested_only else t('common.disabled_word', lang)
        toggle_text = t('admin.feedback.dashboard.toggle', lang, status=status_word)
        # چیدمان دکمه‌ها: دکمه «فقط پیشنهادی‌ها» به‌صورت تکی
        keyboard = [
            [InlineKeyboardButton(toggle_text, callback_data="fb_toggle_suggested")],
            [InlineKeyboardButton(t('admin.feedback.buttons.period', lang), callback_data="fb_change_period")],
            [
                InlineKeyboardButton(t('admin.feedback.buttons.top', lang), callback_data="fb_top"),
                InlineKeyboardButton(t('admin.feedback.buttons.bottom', lang), callback_data="fb_bottom")
            ],
            [
                InlineKeyboardButton(t('admin.feedback.buttons.comments', lang), callback_data="fb_comments"),
                InlineKeyboardButton(t('admin.feedback.buttons.detailed', lang), callback_data="fb_detailed")
            ],
            [
                InlineKeyboardButton(t('admin.feedback.buttons.search', lang), callback_data="fb_search"),
                InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="admin_menu_return")
            ]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @log_user_action("feedback_top_attachments")
    async def show_top_attachments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش محبوب‌ترین اتچمنت‌ها"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # دریافت پارامترهای فیلتر از context
        period = context.user_data.get('fb_period', 30)
        mode = context.user_data.get('fb_mode')
        category = context.user_data.get('fb_category')
        suggested_only = context.user_data.get('fb_suggested_only', False)
        
        # دریافت محبوب‌ترین اتچمنت‌ها
        popular = self.db.get_popular_attachments(
            limit=10,
            days=period,
            mode=mode,
            category=category,
            suggested_only=suggested_only
        )
        
        if not popular:
            text = t('admin.feedback.top.empty', lang)
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")]]
        else:
            text = t('admin.feedback.top.title', lang, days=period) + "\n\n"
            
            for idx, item in enumerate(popular, 1):
                likes = item.get('likes', 0) or 0
                dislikes = item.get('dislikes', 0) or 0
                views = item.get('views', 0) or 0
                net_score = likes - dislikes
                total_votes = likes + dislikes
                like_ratio = (likes / total_votes * 100) if total_votes > 0 else 0
                
                text += f"**{idx}. {item['name']}**\n"
                text += f"   🔤 کد: `{item['code']}`\n"
                text += f"   🔫 سلاح: {item['weapon']} ({CATEGORIES.get(item['category'], item['category'])})\n"
                text += f"   👍 {likes} | 👎 {dislikes} (نمره: {net_score:+d})\n"
                text += f"   📊 نسبت: {like_ratio:.1f}% | 👁 {views:,} بازدید\n\n"
            
            # فیلترهای فعال
            filters = []
            if mode:
                filters.append("🎮 " + t(f"mode.{mode}_short", lang))
            if category:
                filters.append("📂 " + t(f"category.{category}", lang))
            
            if filters:
                text += f"\n🔍 **فیلتر فعال**: {' | '.join(filters)}\n"
            
            keyboard = [
                [InlineKeyboardButton(t('admin.feedback.buttons.change_period', lang), callback_data="fb_change_period")],
                [InlineKeyboardButton(t('admin.feedback.buttons.filter_mode', lang), callback_data="fb_filter_mode")],
                [InlineKeyboardButton(t('admin.feedback.buttons.filter_category', lang), callback_data="fb_filter_category")],
                [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")]
            ]
        
        await query.edit_message_text(
            text[:4096],  # Telegram limit
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @log_user_action("feedback_bottom_attachments")
    async def show_bottom_attachments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش کم‌بازدیدترین یا منفی‌ترین اتچمنت‌ها"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        period = context.user_data.get('fb_period', 30)
        mode = context.user_data.get('fb_mode')
        category = context.user_data.get('fb_category')
        suggested_only = context.user_data.get('fb_suggested_only', False)
        
        # دریافت اتچمنت‌هایی که رأی منفی دارند
        popular = self.db.get_popular_attachments(limit=100, days=period, mode=mode, category=category, suggested_only=suggested_only)
        
        # فیلتر و مرتب‌سازی بر اساس نمره منفی
        negative = [
            item for item in popular 
            if (item['likes'] - item['dislikes']) < 0
        ]
        negative.sort(key=lambda x: x['likes'] - x['dislikes'])
        
        if not negative:
            text = t('admin.feedback.bottom.none', lang)
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")]]
        else:
            text = t('admin.feedback.bottom.title', lang, days=period) + "\n\n"
            text += t('admin.feedback.bottom.note', lang) + "\n\n"
            
            for idx, item in enumerate(negative[:10], 1):
                net_score = item['likes'] - item['dislikes']
                
                text += f"**{idx}. {item['name']}**\n"
                text += f"   🔤 کد: `{item['code']}`\n"
                text += f"   🔫 سلاح: {item['weapon']}\n"
                text += f"   👍 {item['likes']} | 👎 {item['dislikes']} (نمره: {net_score:+d})\n"
                text += f"   👁 {item['views']:,} بازدید\n\n"
            
            text += "\n💡 **پیشنهاد**: این اتچمنت‌ها ممکن است نیاز به بازبینی داشته باشند.\n"
            
            keyboard = [
                [InlineKeyboardButton(t('admin.feedback.buttons.change_period', lang), callback_data="fb_change_period")],
                [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")]
            ]
        
        await query.edit_message_text(
            text[:4096],
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @log_user_action("feedback_search_menu")
    async def show_search_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی جستجو: محبوب‌ترین جستجوها + ابزار فیلتر"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # دریافت محبوب‌ترین جستجوها
        try:
            popular = self.db.get_popular_searches(limit=10)
        except Exception:
            popular = []
        
        text = t('admin.feedback.search.menu.title', lang) + "\n\n" + t('admin.feedback.search.menu.desc', lang) + "\n\n"
        
        keyboard = []
        if popular:
            for q in popular:
                enc = urllib.parse.quote_plus(q)
                label = q if len(q) <= 25 else (q[:25] + "…")
                keyboard.append([InlineKeyboardButton(t('admin.feedback.search.buttons.popular', lang, q=label), callback_data=f"fb_search_q_{enc}")])
        else:
            text += t('admin.feedback.search.menu.no_popular', lang) + "\n\n"
        
        keyboard.append([InlineKeyboardButton(t('admin.feedback.buttons.filter_mode', lang), callback_data="fb_filter_mode")])
        keyboard.append([InlineKeyboardButton(t('admin.feedback.buttons.filter_category', lang), callback_data="fb_filter_category")])
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")])
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @log_user_action("feedback_search_exec")
    async def execute_search_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """اجرای جستجو و نمایش نتایج (تا 10 مورد)"""
        query = update.callback_query
        await query.answer()
        raw = query.data.replace("fb_search_q_", "")
        qtext = urllib.parse.unquote_plus(raw)
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # انجام جستجو
        results = []
        try:
            results = self.db.search_attachments(qtext)
        except Exception as e:
            logger.error(f"Error searching attachments: {e}")
            results = []
        
        if not results:
            text = t('admin.feedback.search.results.none', lang, query=qtext)
        else:
            text = t('admin.feedback.search.results.title', lang, query=qtext) + "\n\n"
            for (category, weapon, mode, att) in results[:10]:
                name = att.get('name')
                code = att.get('code')
                mode_disp = t(f"mode.{mode}_short", lang)
                cat_disp = t(f"category.{category}", lang)
                text += f"• {name} — `{code}`\n   🔫 {weapon} | 📂 {cat_disp} | 🎮 {mode_disp}\n\n"
        
        keyboard = [
            [InlineKeyboardButton(t('admin.feedback.search.buttons.popular_back', lang), callback_data="fb_search")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")]
        ]
        await query.edit_message_text(
            text[:4096],
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    # ========== Filters ==========
    async def filter_mode_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی فیلتر مود (BR/MP/همه)"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        keyboard = [
            [
                InlineKeyboardButton(t('mode.br_short', lang), callback_data="fb_mode_br"),
                InlineKeyboardButton(t('mode.mp_short', lang), callback_data="fb_mode_mp")
            ],
            [InlineKeyboardButton(t('mode.all', lang), callback_data="fb_mode_all")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_top")]
        ]
        await query.edit_message_text(
            t('mode.choose', lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def set_mode_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم فیلتر مود و بازگشت به گزارش محبوب‌ترین"""
        query = update.callback_query
        await query.answer()
        mode = query.data.replace("fb_mode_", "")
        if mode == 'all':
            context.user_data.pop('fb_mode', None)
        else:
            context.user_data['fb_mode'] = mode
        await self.show_top_attachments(update, context)
    
    async def filter_category_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش منوی فیلتر دسته‌ها"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        keyboard = []
        for key, _ in CATEGORIES.items():
            keyboard.append([InlineKeyboardButton(WEAPON_CATEGORIES.get(key, key), callback_data=f"fb_cat_{key}")])
        keyboard.append([InlineKeyboardButton(t('admin.feedback.filter.category.clear', lang), callback_data="fb_cat_clear")])
        keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_top")])
        await query.edit_message_text(
            t('category.choose', lang),
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    async def set_category_filter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنظیم فیلتر دسته و بازگشت به گزارش محبوب‌ترین"""
        query = update.callback_query
        await query.answer()
        data = query.data.replace("fb_cat_", "")
        if data == 'clear':
            context.user_data.pop('fb_category', None)
        else:
            context.user_data['fb_category'] = data
        await self.show_top_attachments(update, context)
    
    @log_user_action("feedback_comments")
    async def show_user_comments(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش نظرات متنی کاربران"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # اگر از دکمه صفحه‌بندی آمده‌ایم، شماره صفحه را ست کن
        if query.data and query.data.startswith("fb_comments_page_"):
            try:
                page = int(query.data.replace("fb_comments_page_", ""))
                context.user_data['fb_comments_page'] = page
            except Exception:
                page = context.user_data.get('fb_comments_page', 1)
        else:
            page = context.user_data.get('fb_comments_page', 1)
        per_page = 5
        suggested_only = context.user_data.get('fb_suggested_only', False)
        
        # دریافت نظرات از دیتابیس
        feedbacks = self._get_user_feedbacks(page=page, per_page=per_page, suggested_only=suggested_only)
        
        if not feedbacks['items']:
            text = t('admin.feedback.comments.empty', lang)
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")]]
        else:
            text = t('admin.feedback.comments.title', lang, page=page, total_pages=feedbacks['total_pages']) + "\n\n"

            for item in feedbacks['items']:
                # محدود کردن طول نظر برای نمایش و ساده‌سازی برای Markdown
                fb_text = item['feedback'] or ''
                feedback_preview = (fb_text[:150] + "...") if len(fb_text) > 150 else fb_text

                # ساخت لینک کاربر: اگر username موجود بود لینک به t.me/username، در غیر اینصورت tg://user?id=
                if item.get('username'):
                    display = f"@{item['username']}"
                    user_link = f"[{display}](https://t.me/{item['username']})"
                else:
                    display = f"User {item['user_id']}"
                    user_link = f"[{display}](tg://user?id={item['user_id']})"

                text += f"👤 {user_link}\n"
                text += f"📎 {item['attachment_name']} — `{item['code']}`\n"
                text += f"💬 {feedback_preview}\n"
                text += f"📅 {item['date']}\n"
                text += "➖➖➖➖➖\n\n"
            
            # دکمه‌های صفحه‌بندی
            keyboard = []
            nav_row = []
            if page > 1:
                nav_row.append(InlineKeyboardButton(t('nav.prev', lang), callback_data=f"fb_comments_page_{page-1}"))
            nav_row.append(InlineKeyboardButton(t('pagination.page_of', lang, page=page, total=feedbacks['total_pages']), callback_data="noop"))
            if page < feedbacks['total_pages']:
                nav_row.append(InlineKeyboardButton(t('nav.next', lang), callback_data=f"fb_comments_page_{page+1}"))
            
            if nav_row:
                keyboard.append(nav_row)
            
            keyboard.append([InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")])
        
        await query.edit_message_text(
            text[:4096],
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @log_user_action("feedback_detailed_stats")
    async def show_detailed_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """نمایش آمار تفصیلی"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        suggested_only = context.user_data.get('fb_suggested_only', False)
        # آمار بر اساس دسته‌بندی/مود با توجه به فیلتر پیشنهادی‌ها
        stats_by_category = self._get_stats_by_category(suggested_only=suggested_only)
        stats_by_mode = self._get_stats_by_mode(suggested_only=suggested_only)
        
        text = t('admin.feedback.detailed.title', lang) + "\n\n"
        text += t('admin.feedback.detailed.modes.title', lang) + "\n"
        for mode, data in stats_by_mode.items():
            mode_name = t(f"mode.{mode}_btn", lang)
            text += t('admin.feedback.detailed.modes.line', lang, mode=mode_name, votes=data['votes'], likes=data['likes'], dislikes=data['dislikes']) + "\n"
        text += "\n" + t('admin.feedback.detailed.categories.title', lang) + "\n"
        for category, data in stats_by_category.items():
            cat_name = t(f"category.{category}", lang)
            avg_score = (data['likes'] - data['dislikes']) / max(data['attachments'], 1)
            text += t('admin.feedback.detailed.categories.line', lang, category=cat_name, attachments=data['attachments'], avg=f"{avg_score:+.1f}") + "\n"
        
        # آمار زمانی
        text += "\n📅 **روند هفتگی:**\n"
        weekly = self._get_weekly_trend(suggested_only=suggested_only)
        for week_data in weekly:
            text += f"• هفته {week_data['week']}: {week_data['votes']:,} رأی جدید\n"
        
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_dashboard")]]
        
        await query.edit_message_text(
            text[:4096],
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    @log_user_action("feedback_change_period")
    async def change_period(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تغییر بازه زمانی گزارش‌ها"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        text = t('admin.feedback.period.title', lang)
        keyboard = [
            [InlineKeyboardButton(t('admin.feedback.period.7', lang), callback_data="fb_period_7")],
            [InlineKeyboardButton(t('admin.feedback.period.30', lang), callback_data="fb_period_30")],
            [InlineKeyboardButton(t('admin.feedback.period.90', lang), callback_data="fb_period_90")],
            [InlineKeyboardButton(t('admin.feedback.period.all', lang), callback_data="fb_period_all")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fb_top")]
        ]
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def set_period(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ذخیره بازه زمانی انتخابی"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # استخراج period از callback_data: fb_period_{days}
        period_str = query.data.replace("fb_period_", "")
        
        if period_str == "all":
            period = 36500  # 100 سال!
            context.user_data['fb_period'] = period
            await query.answer(t('admin.feedback.period.set_all', lang))
        else:
            period = int(period_str)
            context.user_data['fb_period'] = period
            await query.answer(t('admin.feedback.period.set_days', lang, days=period))
        
        # بازگشت به صفحه محبوب‌ترین اتچمنت‌ها
        await self.show_top_attachments(update, context)
    
    # ========== Helper Methods ==========
    
    def _get_global_stats(self, suggested_only: bool = False) -> dict:
        """دریافت آمار کلی سیستم"""
        try:
            # Use proper pooled connection and cursor API (psycopg3)
            dt_filter = get_datetime_interval(30)
            base_sql = (
                f"SELECT "
                f" COUNT(CASE WHEN rating IS NOT NULL THEN 1 END) as total_votes,"
                f" SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) as total_likes,"
                f" SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) as total_dislikes,"
                f" COALESCE(SUM(total_views), 0) as total_views,"
                f" COUNT(CASE WHEN feedback IS NOT NULL AND feedback != '' THEN 1 END) as total_feedbacks,"
                f" COUNT(DISTINCT user_id) as active_users"
                f" FROM user_attachment_engagement"
                f" WHERE last_view_date >= {dt_filter}"
            )
            if suggested_only:
                base_sql += " AND attachment_id IN (SELECT attachment_id FROM suggested_attachments)"

            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(base_sql)
                row = cur.fetchone()
                cur.close()
            return {
                'total_votes': int((row or {}).get('total_votes') or 0),
                'total_likes': int((row or {}).get('total_likes') or 0),
                'total_dislikes': int((row or {}).get('total_dislikes') or 0),
                'total_views': int((row or {}).get('total_views') or 0),
                'total_feedbacks': int((row or {}).get('total_feedbacks') or 0),
                'active_users': int((row or {}).get('active_users') or 0),
            }
        except Exception as e:
            logger.error(f"Error getting global stats: {e}")
            return {
                'total_votes': 0,
                'total_likes': 0,
                'total_dislikes': 0,
                'total_views': 0,
                'total_feedbacks': 0,
                'active_users': 0
            }

    @log_user_action("feedback_toggle_suggested")
    async def toggle_suggested_only(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """روشن/خاموش کردن فیلتر «فقط پیشنهادی‌ها»"""
        query = update.callback_query
        await query.answer()
        current = context.user_data.get('fb_suggested_only', False)
        context.user_data['fb_suggested_only'] = not current
        # بازگشت به داشبورد با وضعیت جدید
        await self.show_feedback_dashboard(update, context)
    
    def _get_user_feedbacks(self, page: int = 1, per_page: int = 5, suggested_only: bool = False) -> dict:
        """دریافت نظرات متنی کاربران با صفحه‌بندی"""
        try:
            # شمارش کل نظرات
            base_count_sql = (
                "SELECT COUNT(*) as count "
                "FROM user_attachment_engagement uae "
                "JOIN attachments a ON uae.attachment_id = a.id "
                "WHERE uae.feedback IS NOT NULL AND uae.feedback != ''"
            )
            if suggested_only:
                base_count_sql += " AND uae.attachment_id IN (SELECT attachment_id FROM suggested_attachments)"

            base_list_sql = (
                "SELECT "
                " uae.user_id,"
                " uae.feedback,"
                " uae.last_view_date,"
                " a.name as attachment_name,"
                " a.code,"
                " u.username,"
                " u.first_name"
                " FROM user_attachment_engagement uae"
                " JOIN attachments a ON uae.attachment_id = a.id"
                " LEFT JOIN users u ON u.user_id = uae.user_id"
                " WHERE uae.feedback IS NOT NULL AND uae.feedback != ''"
            )
            if suggested_only:
                base_list_sql += " AND uae.attachment_id IN (SELECT attachment_id FROM suggested_attachments)"
            base_list_sql += " ORDER BY uae.last_view_date DESC LIMIT %s OFFSET %s"

            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(base_count_sql)
                total_row = cur.fetchone()
                total = int((total_row or {}).get('count') or 0)

                total_pages = max(1, (total + per_page - 1) // per_page)
                offset = (page - 1) * per_page

                cur.execute(base_list_sql, (per_page, offset))
                feedbacks = cur.fetchall() or []
                cur.close()

            def fmt_date(v):
                if not v:
                    return 'نامشخص'
                try:
                    if isinstance(v, datetime):
                        return v.date().isoformat()
                    return str(v)[:10]
                except Exception:
                    return 'نامشخص'

            items = []
            for row in feedbacks:
                items.append({
                    'user_id': row.get('user_id'),
                    'username': row.get('username'),
                    'first_name': row.get('first_name'),
                    'feedback': row.get('feedback'),
                    'date': fmt_date(row.get('last_view_date')),
                    'attachment_name': row.get('attachment_name'),
                    'code': row.get('code'),
                })

            return {
                'items': items,
                'total': total,
                'total_pages': total_pages,
                'current_page': page
            }
        except Exception as e:
            logger.error(f"Error getting user feedbacks: {e}")
            return {'items': [], 'total': 0, 'total_pages': 1, 'current_page': 1}
    
    def _get_stats_by_category(self, suggested_only: bool = False) -> dict:
        """آمار بر اساس دسته‌بندی"""
        try:
            # Attachments don't have category directly; join through weapons -> weapon_categories
            dt_filter = get_datetime_interval(30)
            query = (
                "SELECT "
                " wc.name AS category,"
                " COUNT(DISTINCT a.id) AS attachments,"
                " COALESCE(SUM(CASE WHEN uae.rating = 1 THEN 1 ELSE 0 END), 0) AS likes,"
                " COALESCE(SUM(CASE WHEN uae.rating = -1 THEN 1 ELSE 0 END), 0) AS dislikes"
                " FROM attachments a"
                " JOIN weapons w ON a.weapon_id = w.id"
                " JOIN weapon_categories wc ON w.category_id = wc.id"
                " LEFT JOIN user_attachment_engagement uae ON a.id = uae.attachment_id"
                f" AND uae.last_view_date >= {dt_filter}"
            )
            if suggested_only:
                query += " JOIN suggested_attachments sa ON sa.attachment_id = a.id AND sa.mode = a.mode"
            query += " GROUP BY wc.name ORDER BY likes DESC"

            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query)
                rows = cur.fetchall() or []
                cur.close()

            stats = {}
            for row in rows:
                cat = row['category']
                attachments = row['attachments'] or 0
                likes = row['likes'] or 0
                dislikes = row['dislikes'] or 0
                stats[cat] = {
                    'attachments': attachments,
                    'likes': likes,
                    'dislikes': dislikes
                }
            return stats
        except Exception as e:
            logger.error(f"Error getting stats by category: {e}")
            return {}
    
    def _get_stats_by_mode(self, suggested_only: bool = False) -> dict:
        """آمار بر اساس مود بازی"""
        try:
            dt_filter = get_datetime_interval(30)
            query = (
                "SELECT "
                " a.mode,"
                " COUNT(CASE WHEN uae.rating IS NOT NULL THEN 1 END) AS votes,"
                " COALESCE(SUM(CASE WHEN uae.rating = 1 THEN 1 ELSE 0 END), 0) AS likes,"
                " COALESCE(SUM(CASE WHEN uae.rating = -1 THEN 1 ELSE 0 END), 0) AS dislikes"
                " FROM attachments a"
                " LEFT JOIN user_attachment_engagement uae ON a.id = uae.attachment_id"
                f" AND uae.last_view_date >= {dt_filter}"
            )
            if suggested_only:
                query += " JOIN suggested_attachments sa ON sa.attachment_id = a.id AND sa.mode = a.mode"
            query += " GROUP BY a.mode"

            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query)
                rows = cur.fetchall() or []
                cur.close()

            stats = {}
            for row in rows:
                key = row['mode']
                votes = row['votes'] or 0
                likes = row['likes'] or 0
                dislikes = row['dislikes'] or 0
                stats[key] = {'votes': votes, 'likes': likes, 'dislikes': dislikes}
            return stats
        except Exception as e:
            logger.error(f"Error getting stats by mode: {e}")
            return {}

    def _get_weekly_trend(self, suggested_only: bool = False, weeks: int = 8) -> list:
        """روند هفتگی رأی‌ها در چند هفته اخیر"""
        try:
            days = weeks * 7
            dt_filter = get_datetime_interval(days)
            query = (
                "SELECT "
                " to_char(date_trunc('week', uae.last_view_date), 'IYYY-IW') AS week_label,"
                " COUNT(CASE WHEN uae.rating IS NOT NULL THEN 1 END) AS votes"
                " FROM user_attachment_engagement uae"
            )
            if suggested_only:
                query += (
                    " JOIN attachments a ON a.id = uae.attachment_id"
                    " JOIN suggested_attachments sa ON sa.attachment_id = a.id AND sa.mode = a.mode"
                )
            query += (
                f" WHERE uae.last_view_date >= {dt_filter}"
                " GROUP BY week_label"
                " ORDER BY week_label"
            )

            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query)
                rows = cur.fetchall() or []
                cur.close()

            data = []
            for row in rows:
                wk = row['week_label']
                votes = row['votes'] or 0
                data.append({'week': wk, 'votes': votes})
            return data
        except Exception as e:
            logger.error(f"Error getting weekly trend: {e}")
            return []
