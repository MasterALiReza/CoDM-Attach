# Inline Mode Design — CODM Attachments Bot (PTB v21.5)

این سند طراحی و راهنمای پیاده‌سازی قابلیت Inline Mode برای ربات اتچمنت‌های CODM است؛ طوری که کاربر در گروه با نوشتن `@BotUsername <search>` یا در پی‌وی با تایپ کردن، نتایج اتچمنت‌ها + چند اقدام پیشنهادی (مثل «برترهای فصل» و «تنظیمات بازی») را به‌صورت اینلاین دریافت کند.

هدف: تجربه‌ی «جستجوی سریع و ارسال فوری» بدون خروج از گفتگو، و در عین حال اتصال با منوهای کامل ربات در پی‌وی.

---

## 1) پیش‌نیازها (BotFather)
- **فعال‌سازی Inline:** در BotFather
  - `/setinline` → Enable
  - (اختیاری) `/setinlinefeedback` برای ارسال بازخورد اینلاین
- **Bot Username:** باید تنظیم و پایدار باشد (برای منشن در گروه‌ها، مثل `@Wx_Attach_bot`).
- **Privacy Mode:** برای Inline لازم نیست غیرفعال شود؛ چون Inline Query مستقل از دریافت پیام‌های گروه است. اما برای کار با دکمه‌های Callback در پیام‌های اینلاین مشکلی نیست (CallbackQuery به ربات تحویل داده می‌شود).
- **Deep-link:** استفاده از `start_parameter` برای هدایت کاربر از اینلاین به پی‌وی (Switch to PM).

---

## 2) تجربه‌ی کاربری (UX Flows)
- **Group Inline:** کاربر در گروه می‌نویسد: `@BotUsername ak117` → نتایج اتچمنت‌های مرتبط نمایش می‌شود. با انتخاب هر نتیجه، یک «پیام به نام کاربر، via bot» ارسال می‌شود که شامل:
  - عنوان: نام اتچمنت + سلاح + مود (BR/MP)
  - توضیحات: کد، توضیح کوتاه
  - دکمه‌ها: `📋 کپی کد` (callback: `att_copy_{id}`)، `💬 ثبت نظر`، (اختیاری) `📋 سایر اتچمنت‌های این سلاح`
- **Zero-Query Suggestions:** وقتی کاربر فقط `@BotUsername` را می‌نویسد یا طول جستجو کوتاه است، چند پیشنهاد نمایش می‌دهیم:
  - «⭐ برترهای فصل (BR)» و «⭐ برترهای فصل (MP)»
  - «⚙️ تنظیمات بازی» (با `switch_pm` برای نمایش کامل در پی‌وی)
  - «🎮 اتچمنت کاربران (Browse)»
- **Switch to PM:** در جواب Inline می‌توان `button=InlineQueryResultsButton(text, start_parameter)` داد تا دکمه «باز کردن ربات» نمایش داده شود و با `/start inline` در پی‌وی، منوی اصلی یا یک مسیر مشخص باز شود.

---

## 3) معماری و محل اتصال در کد
پروژه از python-telegram-bot v21.5 و ساختار ماژولار استفاده می‌کند:
- رجیستری‌ها در `app/registry/` ثبت می‌شوند و از `app/factory.BotApplicationFactory` فراخوانی می‌گردند.
- ماژول‌های کاربری در `handlers/user/modules/` موجودند و منطق جستجو در `handlers/user/modules/search/search_handler.py` قابل استفاده‌ی مجدد است.

### 3.1) فایل‌های پیشنهادی جدید (مستندات؛ پیاده‌سازی در فاز بعد)
- `handlers/inline/inline_handler.py`
  - `class InlineHandler(BaseUserHandler)` (یا ماژولی با توابع async مستقل)
  - `handle_inline_query(update, context)`
  - `handle_chosen_inline_result(update, context)`
  - توابع کمکی ساخت نتایج (build results) با استفاده‌ی مجدد از `self.db.search()` و منطق امتیازدهی/اولویت از `SearchHandler`.
- `app/registry/inline_registry.py`
  - ثبت هندلرها:
    - `InlineQueryHandler(inline_handler.handle_inline_query)`
    - `ChosenInlineResultHandler(inline_handler.handle_chosen_inline_result)`
- ویرایش `app/factory.py`
  - در `setup_handlers()`، پس از سایر رجیستری‌ها، `InlineHandlerRegistry(...).register()` اضافه شود تا اینلاین فعال گردد.

نکته: دیتابیس قبلاً در `application.bot_data['database']` ست می‌شود. در هندلر اینلاین هم از همین مسیر یا از `self.bot.db` استفاده کنید تا اتصال یکنواخت باشد.

---

## 4) سیاست نتایج و ساختار داده
- **منبع داده:**
  - جستجو: `db.search(query)` (همانند `SearchHandler.search_process()`)
  - داده‌های تکمیلی: `db.get_all_attachments(...)`, `db.get_top_attachments(...)`, `db.get_season_top_attachments_for_weapon(...)`
- **مرتب‌سازی:** اولویت‌بندی مشابه جستجوی فعلی:
  1) `season_top`  2) `top`  3) `normal`
- **انواع نتیجه (InlineQueryResult):**
  - `InlineQueryResultCachedPhoto` برای اتچمنت‌های دارای تصویر (استفاده از `photo_file_id` موجود در دیتابیس)
  - `InlineQueryResultArticle` برای پیشنهادهای اقدام (برترهای فصل، تنظیمات) با `InputTextMessageContent`
  - **نکته مهم:** چون تصاویر به صورت `image_file_id` در دیتابیس ذخیره می‌شوند، از `InlineQueryResultCachedPhoto` استفاده می‌کنیم نه `thumbnail_url`
- **دکمه‌های هر نتیجه:**
  - `📋 کپی کد` → `callback_data=f"att_copy_{attachment_id}"` (سازگار با هندلرهای موجود در `handlers/user/modules/feedback/feedback_handler.py`)
  - (اختیاری) `💬 ثبت نظر`، `📋 سایر اتچمنت‌های این سلاح`
- **پیشنهادها (Zero-Query):** نتایج «Article» ویژه‌ی اقدام‌ها:
  - «⭐ برترهای فصل (BR/MP)» → محتوای پیام راهنما + دکمه‌های ورودی یا صرفاً دکمه `switch_pm`
  - «⚙️ تنظیمات بازی» → فقط `switch_pm` (نمایش کامل در پی‌وی)

---

## 5) جزئیات PTB v21.5 و API Bot
### 5.1) امضاها و ایمپورت‌ها
- هندلرها:
  - `from telegram.ext import InlineQueryHandler, ChosenInlineResultHandler`
- ساخت نتایج:
  - `from telegram import InlineQueryResultArticle, InlineQueryResultCachedPhoto, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultsButton`
- پاسخ به اینلاین:
  - `await update.inline_query.answer(results, is_personal=True, cache_time=2, button=InlineQueryResultsButton("باز کردن ربات", start_parameter="inline"))`
- رخداد انتخاب نتیجه:
  - `update.chosen_inline_result` → جهت آنالیتیکس و ثبت انتخاب کاربر

### 5.2) اسکلت کدنویسی (نمونه مستنداتی)
```python
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = (update.inline_query.query or "").strip()
    user_id = update.effective_user.id if update.effective_user else None

    results = []
    if len(q) < 2:
        # Zero-Query Suggestions (Top Season, Settings, Browse)
        results = build_suggestions()
    else:
        # Reuse DB search and ranking similar to SearchHandler
        items = context.bot_data['database'].search(q)  # یا self.db.search(q)
        results = build_attachment_results(items)

    # کنترل حجم نتایج
    results = results[:25]

    # Switch to PM button (Deep-link)
    button = InlineQueryResultsButton(text="🔔 باز کردن ربات", start_parameter="inline")

    await update.inline_query.answer(
        results=results, is_personal=True, cache_time=2, button=button
    )

async def handle_chosen_inline_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chosen = update.chosen_inline_result
    # chosen.result_id را لاگ و به آنالیتیکس ارسال کنید
    # در صورت امکان mapping نتیجه به attachment_id برای ثبت view/usage
```

### 5.3) نکات سازگاری Callback در پیام‌های اینلاین
- در پیام‌های اینلاین، ممکن است `CallbackQuery.message` مقدار `None` داشته باشد و فقط `CallbackQuery.inline_message_id` موجود باشد.
- از متدهای wrapper مانند `query.edit_message_caption()` و `query.edit_message_reply_markup()` استفاده کنید؛ این متدها با پیام‌های اینلاین نیز کار می‌کنند.
- اگر جایی به `query.message.caption` یا `query.message.reply_markup` تکیه شده، guard بگذارید و در صورت نبودِ پیام، کیبورد را با `build_feedback_buttons()` بازسازی کنید و caption را از منبع دیگری (DB/متن تولیدی) تأمین کنید.
- دکمه‌های فیدبک (`att_copy_…`, `att_like_…`, `att_dislike_…`, `att_fb_…`) باید بدون وابستگی به `query.message` نیز بدرستی عمل کنند.

> توجه: `result_id` باید یکتا و حداکثر 64 بایت باشد. برای اقلام دیتابیس از `str(attachment_id)` یا `f"att-{id}-{mode}"` استفاده کنید.

### 5.4) عدم استفاده از require_channel_membership در هندلرهای اینلاین
- هندلرهای مربوط به اینلاین (InlineQuery/ChosenInlineResult) را با `require_channel_membership` تزئین نکنید.
- محدودیت عضویت را هنگام نمایش منوها در پی‌وی یا مسیرهای Switch to PM (مثلاً در `/start inline`) اعمال کنید.

---

## 6) کارایی، کش و محدودیت‌ها
- **Cache Time:** `cache_time=2` یا مقدار کم برای نتایج پویا؛ برای پیشنهادهای ثابت می‌توان بیشتر تنظیم کرد.
- **is_personal:** روی `True` باشد تا نتایج برای هر کاربر منفک کش شوند.
- **Rate Limiting:** برای جلوگیری از فشار روی DB، روی طول کوئری حداقل 2 کاراکتر بگذارید، و نتایج را به 25 محدود کنید.
- **حدود تلگرام:**
  - حداکثر 50 نتیجه؛
  - `result_id` ≤ 64 بایت؛
  - سایز کل پاسخ ~10MB؛
  - فرکانس کوئری زیاد است؛ پاسخ‌های سریع و سبک.

---

## 7) امنیت و بهداشت داده
- پاکسازی ورودی (`strip`/طول/کاراکترهای غیرمجاز).
- عدم درج اطلاعات حساس در متن نتایج.
- در Callback ها، وجود داشتن `attachment_id` را چک کنید و خطا را با پیام مناسب هندل کنید.

---

## 8) آنالیتیکس و لاگ‌ها
- ثبت رکورد جستجو در Inline (مشابه `db.track_search`) با زمان پاسخ.
- در `handle_chosen_inline_result`، ثبت انتخاب کاربر (result_id، زمان، chat_type).
- برای نتایج اتچمنت، ثبت `view` مشابه نقاط فعلی (اگر mapping انجام شد).

---

## 9) تست دستی
- **گروهی:**
  - تایپ `@BotUsername` → مشاهده پیشنهادها.
  - تایپ `@BotUsername ak` → بعد از طول 2، نتایج می‌آید.
  - انتخاب یک نتیجه → پیام «via bot» ارسال می‌شود؛ دکمه‌های `📋 کپی کد`، `👍`، `👎` و `💬 ثبت نظر` در پیام اینلاین کار کنند.
- **پی‌وی:**
  - تایپ اینلاین و انتخاب نتیجه.
  - تست دکمه Switch to PM از گروه → باز شدن ربات با `/start inline`.
- **لبه‌ها:**
  - بدون نتیجه؛ خطاهای شبکه؛ سرعت زیاد تایپ.

---

## 10) پلن انتشار
- فعال‌سازی مرحله‌ای Inline در پروفایل بات.
- استقرار کد در شاخه feature با Feature Flag (مثلاً ENV: `INLINE_MODE_ENABLED=true`).
- مانیتور لاگ‌ها و میزان استفاده؛ در صورت مشکل، غیرفعال‌سازی سریع Handler یا برگرداندن Feature Flag.

---

## 11) نقشه‌ی پیاده‌سازی (به ترتیب)
1. ایجاد ماژول: `handlers/inline/inline_handler.py` و پیاده‌سازی دو تابع اصلی.
2. رجیستری جدید: `app/registry/inline_registry.py` و افزودن آن به `app/factory.py`.
3. بازیافت منطق جستجو از `handlers/user/modules/search/search_handler.py` (استفاده از `db.search()` و اولویت‌بندی).
4. پیاده‌سازی `_build_attachment_results()` با `InlineQueryResultCachedPhoto` (استفاده از `image_file_id`).
5. افزودن Switch to PM با `InlineQueryResultsButton("باز کردن ربات", start_parameter="inline")`.
6. اصلاح `handlers/user/modules/navigation/main_menu.py` → `start()` برای handle کردن `context.args` و deep-link.
7. افزودن Feature Flag: `INLINE_MODE_ENABLED` در `.env` برای کنترل فعال/غیرفعال بودن.
8. تست دستی در گروه/پی‌وی و بررسی لاگ‌ها.
9. انتشار تدریجی.

---

## 12) ارجاعات کد موجود
- رجیستری‌ها: `app/registry/` و `app/factory.py`
- جستجو: `handlers/user/modules/search/search_handler.py` → `search_process()` (منطق اولویت‌بندی و ساخت دکمه‌ها)
- دکمه کپی کد: `handlers/user/modules/feedback/feedback_handler.py` → الگوی `att_copy_{id}`
- توابع دیتابیس: `core/database/` (Adapter و Proxy)

---

## 13) FAQ
- **آیا برای Inline باید Privacy Mode خاموش باشد؟** خیر، Inline Query مستقل از دریافت پیام‌های گروه است.
- **آیا می‌توان کیبورد اینلاین به نتیجه افزود؟** بله، برای `InlineQueryResultArticle` و `InlineQueryResultCachedPhoto` می‌توانید `reply_markup=InlineKeyboardMarkup(...)` بدهید؛ دکمه‌های Callback کار می‌کنند.
- **آیا دکمهٔ «باز کردن ربات» در پاسخ اینلاین ممکن است؟** بله، با `InlineQueryResultsButton` و `start_parameter`.
- **آیا می‌توانیم file_id را به جای URL در thumbnail_url استفاده کنیم؟** خیر، `thumbnail_url` باید URL واقعی (http/https) باشد. برای استفاده از file_id از `InlineQueryResultCachedPhoto` با `photo_file_id` استفاده کنید.
- **چرا InlineQueryResultCachedPhoto به جای Article با thumb_url؟** چون دیتابیس ما فقط `image_file_id` ذخیره می‌کند، نه URL. `CachedPhoto` مستقیماً با file_id کار می‌کند.

