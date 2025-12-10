from telegram import Update, InlineQueryResultArticle, InlineQueryResultCachedPhoto, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultsButton
from telegram.ext import ContextTypes
from config.config import GAME_MODES
from utils.language import get_user_lang
from utils.i18n import t
from handlers.user.base_user_handler import BaseUserHandler
from utils.subscribers_pg import SubscribersPostgres as Subscribers
from datetime import datetime, timezone, timedelta
from core.cache.smart_cache import get_smart_cache
import os
import re


class InlineHandler(BaseUserHandler):
    def __init__(self, db):
        super().__init__(db)
        self.article_only = os.getenv('INLINE_USE_ARTICLE_ONLY', 'false').lower() == 'true'
        self.photo_require_start = os.getenv('INLINE_PHOTO_REQUIRE_START', 'false').lower() == 'true'

    async def handle_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import logging
        logger = logging.getLogger(__name__)
        
        q = (update.inline_query.query or "").strip()
        user_id = update.effective_user.id if update.effective_user else None
        logger.info(f"Inline query from user {user_id}: '{q}'")

        results = []
        # تشخیص نوع چت برای جلوگیری از نمایش «ثبت نظر» در گروه‌ها
        try:
            chat_type = getattr(update.inline_query, 'chat_type', None)
        except Exception:
            chat_type = None
        is_group = chat_type in ('group', 'supergroup')
        if len(q) < 2:
            results = self._build_suggestions()
            logger.info(f"Query too short, returning {len(results)} suggestions")
        else:
            try:
                items = self.db.search(q)
                logger.info(f"Search found {len(items)} items")
                bot_username = None
                try:
                    bot_username = context.bot.username
                except Exception:
                    pass
                if not bot_username:
                    bot_username = os.getenv('BOT_USERNAME', '')
                try:
                    started = Subscribers(db_adapter=self.db).is_subscribed(user_id)
                    logger.info(f"User {user_id} started: {started}")
                except Exception as e:
                    logger.error(f"Error checking subscription: {e}")
                    started = False
                # حالت ویژه: اگر کوئری به شکل att:ID[-mode] بود، یک نتیجه عکس دار برگردان
                special_match = re.match(r"(?i)^att[:\-\s]*(\d+)(?:[\-\s_]+(br|mp))?$", q)
                if special_match:
                    try:
                        att_id = int(special_match.group(1))
                        mode = (special_match.group(2) or 'br').lower()
                    except Exception:
                        att_id, mode = None, 'br'
                    results = []
                    if att_id:
                        att = self.db.get_attachment_by_id(att_id)
                        if att and att.get('image'):
                            try:
                                stats = self.db.get_attachment_stats(att_id, period='all') or {}
                                like_count = stats.get('like_count', 0)
                                dislike_count = stats.get('dislike_count', 0)
                            except Exception:
                                like_count = dislike_count = 0
                            weapon = att.get('weapon') or ''
                            lang = get_user_lang(update, context, self.db) or 'fa'
                            mode_name = t(f"mode.{mode}", lang)
                            # برای پیام عکس در گروه: فقط دکمه‌های فیدبک + ارسال در پی‌وی + ارسال عکس در گروه
                            rows = [
                                [InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"), InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")]
                            ]
                            if is_group and bot_username:
                                rows.append([InlineKeyboardButton(t("inline.send_in_pm", lang), url=f"https://t.me/{bot_username}?start=att-{att_id}-{mode}")])
                            if is_group:
                                rows.append([InlineKeyboardButton(t("inline.send_photo_in_group", lang), switch_inline_query_current_chat=f"att:{att_id}-{mode}")])
                            results.append(InlineQueryResultCachedPhoto(
                                id=f"att-{att_id}-{mode}",
                                photo_file_id=att['image'],
                                title=f"{att.get('name','?')} ({weapon})",
                                description=f"{t('attachment.code', lang)}: {att.get('code','')} | {mode_name}",
                                caption=f"**{att.get('name','')}**\n{t('attachment.code', lang)}: `{att.get('code','')}`\n{weapon} | {mode_name}",
                                parse_mode='Markdown',
                                reply_markup=InlineKeyboardMarkup(rows)
                            ))
                        else:
                            # اگر عکس ندارد، از مسیر عادی ادامه بده
                            pass
                else:
                    results = self._build_weapon_recent_and_lists(
                        q=q,
                        items=items,
                        bot_username=bot_username,
                        started=started,
                        is_group=is_group
                    )
                logger.info(f"Built {len(results)} results")
                if user_id:
                    try:
                        self.db.track_search(user_id, q, int(len(results)), 0.0)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"Error in inline query: {e}")
                import traceback
                traceback.print_exc()

        results = results[:25]
        logger.info(f"Sending {len(results)} results to user")

        lang = get_user_lang(update, context, self.db) or 'fa'
        button = InlineQueryResultsButton(text=t("inline.open_bot", lang), start_parameter="inline")
        await update.inline_query.answer(results=results, is_personal=True, cache_time=2, button=button)

    async def handle_chosen_inline_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        import logging
        logger = logging.getLogger(__name__)
        result = update.chosen_inline_result
        result_id = result.result_id if result else None
        # fallback: اگر effective_user نداشت، از from_user در chosen_inline_result بگیر
        user_id = update.effective_user.id if update.effective_user else (
            (getattr(result, 'from_user', None).id if (result and getattr(result, 'from_user', None)) else None)
        )
        logger.info(f"ChosenInlineResult received: result_id={result_id}, user_id={user_id}, inline_message_id={getattr(result, 'inline_message_id', None)}")
        if not result_id or not user_id:
            logger.warning("ChosenInlineResult missing result_id or user_id; skipping")
            return
        try:
            started = Subscribers(db_adapter=self.db).is_subscribed(user_id)
        except Exception:
            started = False

        if result_id.startswith("att-"):
            parts = result_id.split("-")
            if len(parts) >= 3:
                try:
                    att_id = int(parts[1])
                    mode = parts[2]
                except Exception:
                    att_id = None
                    mode = 'br'
                if att_id:
                    # فقط ثبت بازدید؛ هیچ ارسال خودکاری به پی‌وی انجام نمی‌شود
                    try:
                        self.db.track_attachment_view(user_id, att_id)
                    except Exception:
                        pass
        elif result_id.startswith("allw-"):
            try:
                payload = result_id.replace("allw-", "")
                category, weapon, mode = payload.split("__", 2)
            except Exception:
                category = weapon = None
                mode = 'br'
            if category and weapon and not started:
                await self._send_weapon_list_pm(context, user_id, category, weapon, mode)

    def _select_best_weapon(self, q: str, items):
        """انتخاب بهترین سلاح منطبق با کوئری از میان نتایج search"""
        if not items:
            return None
        ql = q.lower()
        uniques = []  # [(category, weapon)]
        for it in items:
            category = None
            weapon = None
            # حالت dict-row
            try:
                category = it.get('category')
                weapon = it.get('weapon')
            except Exception:
                category = category or None
                weapon = weapon or None
            if not category or not weapon:
                continue
            key = (category, weapon)
            if key not in uniques and category and weapon:
                uniques.append(key)
        # اولویت: برابر کامل، سپس شامل شدن
        exact = next((w for w in uniques if w[1].lower() == ql), None)
        if exact:
            return exact
        contains = next((w for w in uniques if ql in (w[1] or '').lower()), None)
        if contains:
            return contains
        return uniques[0] if uniques else None

    def _build_weapon_recent_and_lists(self, q: str, items, bot_username: str, started: bool, is_group: bool = False):
        import logging
        logger = logging.getLogger(__name__)
        
        best = self._select_best_weapon(q, items)
        logger.info(f"Best weapon selected: {best}")
        if not best:
            logger.warning("No best weapon found, returning empty results")
            return []
        category, weapon = best
        results = []
        recent_count = 0
        try:
            recent_count = int(os.getenv('INLINE_RECENT_COUNT', '2'))
        except Exception:
            recent_count = 2
        for mode in ['br', 'mp']:
            mode_name = GAME_MODES.get(mode, mode)
            atts = self.db.get_all_attachments(category, weapon, mode=mode) or []
            logger.info(f"Fetched {len(atts)} attachments for {weapon} ({mode})")
            def sort_key(a):
                return (
                    a.get('created_at') or 0,
                    a.get('id') or 0
                )
            try:
                atts_sorted = sorted(atts, key=sort_key, reverse=True)
            except Exception:
                atts_sorted = list(reversed(atts))
            for att in atts_sorted[:recent_count]:
                att_id = att.get('id')
                if not att_id:
                    continue
                title = f"{('🪂' if mode=='br' else '🎮')} {att.get('name','?')} ({weapon})"
                desc = f"{t('attachment.code', lang)}: {att.get('code','')} | {t(f'mode.{mode}', lang)}"
                try:
                    stats = self.db.get_attachment_stats(att_id, period='all') or {}
                    like_count = stats.get('like_count', 0)
                    dislike_count = stats.get('dislike_count', 0)
                except Exception:
                    like_count = dislike_count = 0
                kb_rows = [
                    [InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"), InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")]
                ]
                if not is_group:
                    kb_rows.append([InlineKeyboardButton("📋 کپی کد", callback_data=f"att_copy_{att_id}")])
                    kb_rows.append([InlineKeyboardButton("💬 ثبت نظر", callback_data=f"att_fb_{att_id}")])
                if bot_username:
                    kb_rows.append([InlineKeyboardButton(t("inline.send_in_pm", lang), url=f"https://t.me/{bot_username}?start=att-{att_id}-{mode}")])
                # دکمه ویژه برای ارسال عکس در گروه با باز کردن اینلاین با کوئری att:id
                kb_rows.append([InlineKeyboardButton(t("inline.send_photo_in_group", lang), switch_inline_query_current_chat=f"att:{att_id}-{mode}")])
                kb = InlineKeyboardMarkup(kb_rows)
                has_image = bool(att.get('image'))
                logger.info(f"Processing attachment {att_id}: started={started}, has_image={has_image}")
                
                # همیشه از Article استفاده کن تا thumbnail نباشد
                if started:
                    text = f"**{att.get('name','')}**\n{t('attachment.code', lang)}: `{att.get('code','')}`\n{weapon} | {mode_name}"
                else:
                    text = t("error.generic", lang)
                results.append(InlineQueryResultArticle(
                    id=f"att-{att_id}-{mode}",
                    title=title,
                    input_message_content=InputTextMessageContent(
                        message_text=text,
                        parse_mode='Markdown'
                    ),
                    description=desc,
                    reply_markup=kb,
                ))
        for mode in ['br', 'mp']:
            mode_name = GAME_MODES.get(mode, mode)
            if started:
                atts2 = self.db.get_all_attachments(category, weapon, mode=mode) or []
                if not atts2:
                    text2 = t('attachment.none', lang)
                else:
                    lines2 = [t('attachment.all.header', lang, weapon=weapon) + f" ({mode_name})"]
                    for i, att in enumerate(atts2[:20], start=1):
                        lines2.append(f"{i}. {att.get('name','?')} — `{att.get('code','')}`")
                    text2 = "\n".join(lines2)
                results.append(InlineQueryResultArticle(
                    id=f"allw-{category}__{weapon}__{mode}",
                    title=t('attachment.all.header', lang, weapon=weapon) + f" ({t(f'mode.{mode}_short', lang)})",
                    input_message_content=InputTextMessageContent(
                        message_text=text2,
                        parse_mode='Markdown'
                    ),
                    description=f"{weapon} ({mode.upper()})",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(t('inline.send_in_pm', lang), url=f"https://t.me/{bot_username}?start=allw-{category}__{weapon}__{mode}")]
                    ]) if bot_username else None,
                ))
            else:
                info2 = t('error.generic', lang)
                results.append(InlineQueryResultArticle(
                    id=f"allw-{category}__{weapon}__{mode}",
                    title=t('attachment.all.header', lang, weapon=weapon) + f" ({t(f'mode.{mode}_short', lang)})",
                    input_message_content=InputTextMessageContent(
                        message_text=info2,
                        parse_mode='Markdown'
                    ),
                    description=f"{weapon} ({mode.upper()})",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(t('inline.send_in_pm', lang), url=f"https://t.me/{bot_username}?start=allw-{category}__{weapon}__{mode}")]
                    ]) if bot_username else None,
                ))
        return results[:25]

    def _build_weapon_recent_results(self, q: str, items, bot_username: str):
        """ساخت نتایج: 5 اتچمنت آخر هر مود (BR/MP) برای سلاح انتخاب‌شده"""
        best = self._select_best_weapon(q, items)
        if not best:
            return []
        category, weapon = best
        results = []
        for mode in ['br', 'mp']:
            atts = self.db.get_all_attachments(category, weapon, mode=mode) or []
            # مرتب‌سازی: created_at DESC اگر موجود بود، در غیر اینصورت id DESC
            def sort_key(a):
                return (
                    a.get('created_at') or 0,
                    a.get('id') or 0
                )
            try:
                atts_sorted = sorted(atts, key=sort_key, reverse=True)
            except Exception:
                atts_sorted = list(reversed(atts))
            for att in atts_sorted[:5]:
                att_id = att.get('id')
                if not att_id:
                    continue
                title = f"{('🪂' if mode=='br' else '🎮')} {att.get('name','?')} ({weapon})"
                desc = f"کد: {att.get('code','')} | {('بتل رویال' if mode=='br' else 'مولتی')}"
                can_use_photo = bool(att.get('image')) and not self.article_only
                if can_use_photo:
                    # شمارنده‌های لایک/دیس‌لایک برای نمایش زیر عکس
                    try:
                        stats = self.db.get_attachment_stats(att_id, period='all') or {}
                        like_count = stats.get('like_count', 0)
                        dislike_count = stats.get('dislike_count', 0)
                    except Exception:
                        like_count = dislike_count = 0
                    results.append(InlineQueryResultCachedPhoto(
                        id=f"att-{att_id}-{mode}",
                        photo_file_id=att['image'],
                        title=title,
                        description=desc,
                        caption=f"**{att.get('name','')}**\nکد: `{att.get('code','')}`\n{weapon} | {('🪂 بتل رویال' if mode=='br' else '🎮 مولتی پلیر')}",
                        parse_mode='Markdown',
                        reply_markup=InlineKeyboardMarkup(
                            ([ [InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"), InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}") ] ])
                            + ( [[InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=att-{att_id}-{mode}")]] if bot_username else [] )
                            + [[InlineKeyboardButton("🖼 ارسال عکس در گروه", switch_inline_query_current_chat=f"att:{att_id}-{mode}")]]
                        )
                    ))
                else:
                    results.append(InlineQueryResultArticle(
                        id=f"att-{att_id}-{mode}",
                        title=title,
                        input_message_content=InputTextMessageContent(
                            message_text=f"**{att.get('name','')}**\nکد: `{att.get('code','')}`\n{weapon} | {('🪂 بتل رویال' if mode=='br' else '🎮 مولتی پلیر')}",
                            parse_mode='Markdown'
                        ),
                        description=desc,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=att-{att_id}-{mode}")]
                        ]) if bot_username else None,
                    ))
        # در انتها، یک مورد برای «همه اتچمنت‌ها» نیز اضافه می‌کنیم
        results.append(InlineQueryResultArticle(
            id=f"allw-{category}__{weapon}__br",
            title=f"📋 همه اتچمنت‌های {weapon} (🪂 بتل)",
            input_message_content=InputTextMessageContent(
                message_text=f"در حال ارسال لیست اتچمنت‌های {weapon} (🪂 بتل)...",
                parse_mode='Markdown'
            ),
            description="لیست کامل این سلاح (BR)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=allw-{category}__{weapon}__br")]
            ]) if bot_username else None,
        ))
        results.append(InlineQueryResultArticle(
            id=f"allw-{category}__{weapon}__mp",
            title=f"📋 همه اتچمنت‌های {weapon} (🎮 مولتی)",
            input_message_content=InputTextMessageContent(
                message_text=f"در حال ارسال لیست اتچمنت‌های {weapon} (🎮 مولتی)...",
                parse_mode='Markdown'
            ),
            description="لیست کامل این سلاح (MP)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=allw-{category}__{weapon}__mp")]
            ]) if bot_username else None,
        ))
        return results[:25]

    def _select_top_weapons(self, q: str, items, max_weapons: int = 2):
        if not items:
            return []
        ql = (q or '').lower()
        uniques = []  # [(category, weapon)]
        for it in items:
            category = None
            weapon = None
            # dict-row
            try:
                category = it.get('category')
                weapon = it.get('weapon')
            except Exception:
                pass
            if not category or not weapon:
                continue
            key = (category, weapon)
            if key not in uniques and category and weapon:
                uniques.append(key)
        def rank(pair):
            w = (pair[1] or '').lower()
            if w == ql:
                return 100
            if w.startswith(ql) and ql:
                return 60
            if ql in w and ql:
                return 30
            return 0
        ranked = sorted(uniques, key=rank, reverse=True)
        return ranked[:max_weapons]

    def _build_multi_weapon_recent_results(self, q: str, items, bot_username: str, max_weapons: int = 2, remaining_quota: int = 0, user_id: int = None, started: bool = False):
        selected = self._select_top_weapons(q, items, max_weapons=max_weapons)
        if not selected:
            return []
        results = []
        for (category, weapon) in selected:
            for mode in ['br', 'mp']:
                atts = self.db.get_all_attachments(category, weapon, mode=mode) or []
                def sort_key(a):
                    return (
                        a.get('created_at') or 0,
                        a.get('id') or 0
                    )
                try:
                    atts_sorted = sorted(atts, key=sort_key, reverse=True)
                except Exception:
                    atts_sorted = list(reversed(atts))
                for att in atts_sorted[:5]:
                    att_id = att.get('id')
                    if not att_id:
                        continue
                    title = f"{('🪂' if mode=='br' else '🎮')} {att.get('name','?')} ({weapon})"
                    desc = f"کد: {att.get('code','')} | {('بتل رویال' if mode=='br' else 'مولتی')}"
                    can_use_photo = bool(att.get('image')) and (remaining_quota > 0) and not self.article_only and started
                    # دکمه‌ها (با فیدبک)
                    kb = None
                    try:
                        stats = self.db.get_attachment_stats(att_id, period='all') or {}
                        like_count = stats.get('like_count', 0)
                        dislike_count = stats.get('dislike_count', 0)
                    except Exception:
                        like_count = dislike_count = 0
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"), InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")],
                        ([InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=att-{att_id}-{mode}")] if bot_username else [])
                    ] + [[InlineKeyboardButton("🖼 ارسال عکس در گروه", switch_inline_query_current_chat=f"att:{att_id}-{mode}")]])
                    if can_use_photo:
                        remaining_quota -= 1
                        self._use_inline_photo_quota(user_id, 1)
                        results.append(InlineQueryResultCachedPhoto(
                            id=f"att-{att_id}-{mode}",
                            photo_file_id=att['image'],
                            title=title,
                            description=desc,
                            caption=f"**{att.get('name','')}**\nکد: `{att.get('code','')}`\n{weapon} | {('🪂 بتل رویال' if mode=='br' else '🎮 مولتی پلیر')}",
                            parse_mode='Markdown',
                            reply_markup=kb
                        ))
                    else:
                        results.append(InlineQueryResultArticle(
                            id=f"att-{att_id}-{mode}",
                            title=title,
                            input_message_content=InputTextMessageContent(
                                message_text=f"**{att.get('name','')}**\nکد: `{att.get('code','')}`\n{weapon} | {('🪂 بتل رویال' if mode=='br' else '🎮 مولتی پلیر')}",
                                parse_mode='Markdown'
                            ),
                            description=desc,
                            reply_markup=kb,
                        ))
            # لینک «همه اتچمنت‌ها» برای هر سلاح
            results.append(InlineQueryResultArticle(
                id=f"allw-{category}__{weapon}__br",
                title=f"📋 همه اتچمنت‌های {weapon} (🪂 بتل)",
                input_message_content=InputTextMessageContent(
                    message_text=f"در حال ارسال لیست اتچمنت‌های {weapon} (🪂 بتل)...",
                    parse_mode='Markdown'
                ),
                description="لیست کامل این سلاح (BR)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=allw-{category}__{weapon}__br")]
                ]) if bot_username else None,
            ))
            results.append(InlineQueryResultArticle(
                id=f"allw-{category}__{weapon}__mp",
                title=f"📋 همه اتچمنت‌های {weapon} (🎮 مولتی)",
                input_message_content=InputTextMessageContent(
                    message_text=f"در حال ارسال لیست اتچمنت‌های {weapon} (🎮 مولتی)...",
                    parse_mode='Markdown'
                ),
                description="لیست کامل این سلاح (MP)",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=allw-{category}__{weapon}__mp")]
                ]) if bot_username else None,
            ))
        return results[:25]

    def _build_attachment_results(self, items, bot_username: str, remaining_quota: int = 0, user_id: int = None, started: bool = False, is_group: bool = False):
        results = []
        if not items:
            return results

        unique_sets = set()
        for item in items[:25]:
            try:
                attachment = item.get('attachment')
                weapon = item.get('weapon')
                mode = item.get('mode')
                category = item.get('category')
            except Exception:
                continue
            if not attachment:
                continue
            att_id = attachment.get('id')
            if not att_id:
                continue

            # دکمه‌ها با فیدبک
            try:
                stats = self.db.get_attachment_stats(att_id, period='all') or {}
                like_count = stats.get('like_count', 0)
                dislike_count = stats.get('dislike_count', 0)
            except Exception:
                like_count = dislike_count = 0
            keyboard = [
                [InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"), InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")]
            ]
            if not is_group:
                keyboard.append([InlineKeyboardButton("📋 کپی کد", callback_data=f"att_copy_{att_id}")])
                keyboard.append([InlineKeyboardButton("💬 ثبت نظر", callback_data=f"att_fb_{att_id}")])

            mode_name = GAME_MODES.get(mode, mode)
            can_use_photo = bool(attachment.get('image')) and (remaining_quota > 0) and not self.article_only and started
            if can_use_photo:
                remaining_quota -= 1
                self._use_inline_photo_quota(user_id, 1)
                results.append(InlineQueryResultCachedPhoto(
                    id=f"att-{att_id}-{mode}",
                    photo_file_id=attachment['image'],
                    title=f"{attachment['name']} ({weapon})",
                    description=f"کد: {attachment['code']} | {mode_name}",
                    reply_markup=InlineKeyboardMarkup(
                        [ [InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"), InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}") ] ]
                        + ( [[InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=att-{att_id}-{mode}")]] if bot_username else [] )
                        + [[InlineKeyboardButton("🖼 ارسال عکس در گروه", switch_inline_query_current_chat=f"att:{att_id}-{mode}")]]
                    ),
                    caption=f"**{attachment['name']}**\nکد: `{attachment['code']}`\n{weapon} | {mode_name}",
                    parse_mode='Markdown'
                ))
            else:
                results.append(InlineQueryResultArticle(
                    id=f"att-{att_id}-{mode}",
                    title=f"{attachment['name']} ({weapon})",
                    input_message_content=InputTextMessageContent(
                        message_text=f"**{attachment['name']}**\nکد: `{attachment['code']}`\n{weapon} | {mode_name}",
                        parse_mode='Markdown'
                    ),
                    description=f"کد: {attachment['code']}",
                    reply_markup=InlineKeyboardMarkup(
                        keyboard
                        + ([[InlineKeyboardButton("📥 ارسال در پی‌وی", url=f"https://t.me/{bot_username}?start=att-{att_id}-{mode}")]] if bot_username else [])
                        + [[InlineKeyboardButton("🖼 ارسال عکس در گروه", switch_inline_query_current_chat=f"att:{att_id}-{mode}")]]
                    )
                ))

            try:
                unique_sets.add((category, weapon, mode))
            except Exception:
                pass

        for (category, weapon, mode) in list(unique_sets)[:5]:
            mode_name = GAME_MODES.get(mode, mode)
            results.append(InlineQueryResultArticle(
                id=f"allw-{category}__{weapon}__{mode}",
                title=f"📋 همه اتچمنت‌های {weapon} ({mode_name})",
                input_message_content=InputTextMessageContent(
                    message_text=f"در حال ارسال لیست اتچمنت‌های {weapon} ({mode_name})...",
                    parse_mode='Markdown'
                ),
                description="لیست کامل این سلاح",
            ))
        return results

    # ======== Inline Photo Daily Quota (per user) ========
    def _quota_key(self, user_id: int) -> str:
        today = datetime.now(timezone.utc).date().isoformat()
        return f"inline_photo_used:{today}:{user_id}"

    def _get_user_inline_photo_quota(self, user_id: int, daily_limit: int) -> int:
        if not user_id:
            return 0
        cache = get_smart_cache()
        key = self._quota_key(user_id)
        data = cache.get(key) or {'used': 0}
        used = int(data.get('used', 0))
        remaining = max(0, int(daily_limit) - used)
        return remaining

    def _use_inline_photo_quota(self, user_id: int, count: int = 1):
        if not user_id or count <= 0:
            return
        cache = get_smart_cache()
        key = self._quota_key(user_id)
        data = cache.get(key) or {'used': 0}
        data['used'] = int(data.get('used', 0)) + count
        # TTL تا انتهای روز (UTC)
        now = datetime.now(timezone.utc)
        tomorrow = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
        ttl = int((tomorrow - now).total_seconds())
        cache.set(key, data, data_type='user_data', ttl=max(60, ttl))

    def _build_suggestions(self):
        return [
            InlineQueryResultArticle(
                id="suggestion-top-br",
                title="⭐ برترهای فصل (بتل رویال)",
                input_message_content=InputTextMessageContent(
                    message_text="برای مشاهده برترین اتچمنت‌های فصل، از منوی ربات استفاده کنید.",
                ),
                description="مشاهده برترین‌های BR",
            ),
            InlineQueryResultArticle(
                id="suggestion-top-mp",
                title="⭐ برترهای فصل (مولتی)",
                input_message_content=InputTextMessageContent(
                    message_text="برای مشاهده برترین‌های فصل مولتی، از منوی ربات استفاده کنید.",
                ),
                description="مشاهده برترین‌های MP",
            ),
        ]

    async def _send_attachment_pm(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, attachment: dict, mode: str):
        import logging
        logger = logging.getLogger(__name__)
        
        mode_name = GAME_MODES.get(mode, mode)
        weapon = attachment.get('weapon') or attachment.get('weapon_name') or ''
        caption = f"**{attachment.get('name','')}**\nکد: `{attachment.get('code','')}`\n{weapon} | {mode_name}"
        att_id = attachment.get('id')
        kb = None
        if att_id:
            try:
                stats = self.db.get_attachment_stats(att_id, period='all') or {}
                like_count = stats.get('like_count', 0)
                dislike_count = stats.get('dislike_count', 0)
            except Exception:
                like_count = dislike_count = 0
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                    InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
                ],
                [InlineKeyboardButton("📋 کپی کد", callback_data=f"att_copy_{att_id}")],
                [InlineKeyboardButton("💬 ثبت نظر", callback_data=f"att_fb_{att_id}")]
            ])
        try:
            if attachment.get('image'):
                logger.info(f"Attempting to send photo with file_id: {attachment['image'][:50]}... to chat {chat_id}")
                await context.bot.send_photo(chat_id=chat_id, photo=attachment['image'], caption=caption, parse_mode='Markdown', reply_markup=kb)
                logger.info(f"Photo sent successfully to chat {chat_id}")
            else:
                logger.info(f"No image for attachment {att_id}, sending text only")
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode='Markdown', reply_markup=kb)
        except Exception as e:
            logger.error(f"Error sending photo to PM: {e}. Falling back to text message.")
            try:
                await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode='Markdown', reply_markup=kb)
            except Exception as e2:
                logger.error(f"Error sending fallback text message: {e2}")

    async def _send_attachment_pm_with_share(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, attachment: dict, mode: str):
        """ارسال اتچمنت در PM با دکمه اشتراک‌گذاری در گروه"""
        import logging
        logger = logging.getLogger(__name__)
        
        mode_name = GAME_MODES.get(mode, mode)
        weapon = attachment.get('weapon') or attachment.get('weapon_name') or ''
        caption = f"**{attachment.get('name','')}**\nکد: `{attachment.get('code','')}` \n{weapon} | {mode_name}"
        att_id = attachment.get('id')
        
        # دکمه‌های فیدبک + دکمه اشتراک‌گذاری در گروه
        kb = None
        if att_id:
            try:
                stats = self.db.get_attachment_stats(att_id, period='all') or {}
                like_count = stats.get('like_count', 0)
                dislike_count = stats.get('dislike_count', 0)
            except Exception:
                like_count = dislike_count = 0
            
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            # دکمه اشتراک‌گذاری با switch_inline_query که به گروه برمی‌گردد
            share_query = f"{weapon}"
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"👍 {like_count}", callback_data=f"att_like_{att_id}"),
                    InlineKeyboardButton(f"👎 {dislike_count}", callback_data=f"att_dislike_{att_id}")
                ],
                [InlineKeyboardButton("📋 کپی کد", callback_data=f"att_copy_{att_id}")],
                [InlineKeyboardButton("💬 ثبت نظر", callback_data=f"att_fb_{att_id}")],
                [InlineKeyboardButton("🔄 اشتراک‌گذاری در گروه", switch_inline_query=share_query)]
            ])
        
        try:
            if attachment.get('image'):
                logger.info(f"Sending photo with share button to chat {chat_id}")
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=attachment['image'],
                    caption=caption,
                    parse_mode='Markdown',
                    reply_markup=kb
                )
                logger.info(f"Photo with share button sent successfully")
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    parse_mode='Markdown',
                    reply_markup=kb
                )
        except Exception as e:
            logger.error(f"Error sending attachment to PM: {e}")
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=caption,
                    parse_mode='Markdown',
                    reply_markup=kb
                )
            except Exception as e2:
                logger.error(f"Error sending fallback message: {e2}")

    async def _send_weapon_list_pm(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, category: str, weapon: str, mode: str):
        items = self.db.get_all_attachments(category, weapon, mode=mode)
        mode_name = GAME_MODES.get(mode, mode)
        if not items:
            try:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ برای {weapon} ({mode_name}) اتچمنتی یافت نشد.")
            except Exception:
                pass
            return
        lines = [f"**📋 لیست اتچمنت‌های {weapon} ({mode_name})**"]
        for i, att in enumerate(items[:20], start=1):
            lines.append(f"{i}. {att.get('name','?')} — `{att.get('code','')}`")
        text = "\n".join(lines)
        try:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        except Exception:
            pass
