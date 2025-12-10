# بررسی عمیق سند Inline Mode نسبت به پروژه

## ✅ موارد تأیید شده (صحیح و قابل پیاده‌سازی)

### 1. **PTB v21.5 API**
- ✅ `InlineQueryHandler` موجود و قابل استفاده است
- ✅ `ChosenInlineResultHandler` موجود است
- ✅ `InlineQueryResultsButton` در v21.5 موجود است با امضای:
  ```python
  InlineQueryResultsButton(text, web_app=None, start_parameter=None)
  ```
- ✅ `InlineQueryResultArticle` با پارامتر `thumbnail_url` موجود است
- ✅ `InputTextMessageContent` برای محتوای پیام موجود است
- ✅ پارامتر `button` در `inline_query.answer()` قابل استفاده است

### 2. **دسترسی به دیتابیس**
- ✅ `context.bot_data['database']` در `main.py` و `app/factory.py` تنظیم می‌شود (خط 280 main.py، خط 67 factory.py)
- ✅ می‌توان از `self.db` در کلاس‌های BaseUserHandler استفاده کرد

### 3. **توابع دیتابیس مورد نیاز**
- ✅ `db.search(query)` موجود است (`database_adapter.py` خط 622)
- ✅ `db.track_search(user_id, query, results_count, execution_time_ms)` موجود است
- ✅ `db.get_season_top_attachments(mode)` موجود است
- ✅ `db.get_season_top_attachments_for_weapon(category, weapon, mode)` موجود است
- ✅ `db.get_all_attachments(category, weapon, mode)` موجود است
- ✅ `db.get_top_attachments(category, weapon, mode)` موجود است

### 4. **الگوهای موجود در کد**
- ✅ الگوی `att_copy_{id}` در `FeedbackHandler` پیاده شده (`feedback_handler.py`)
- ✅ الگوی `qatt_{category}__{weapon}__{mode}__{code}` در جستجو موجود است
- ✅ منطق اولویت‌بندی (season_top > top > normal) در `SearchHandler.search_process()` موجود است

### 5. **معماری پروژه**
- ✅ ساختار Registry/Factory موجود و کاملاً سازگار با پیشنهاد سند
- ✅ پوشه `app/registry/` برای ثبت هندلرها استفاده می‌شود
- ✅ `BotApplicationFactory` در `app/factory.py` برای setup handlers استفاده می‌شود
- ✅ ساختار `BaseUserHandler` برای توابع مشترک موجود است

---

## ⚠️ موارد نیازمند اصلاح یا توضیح بیشتر

### 1. **تصاویر اتچمنت‌ها: file_id نه URL**
**مشکل:** سند پیشنهاد استفاده از `thumb_url` را داده، اما در دیتابیس فقط `image_file_id` ذخیره می‌شود.

**واقعیت کد:**
```python
# database_pg_proxy.py - تمام queries شامل image_file_id هستند
SELECT a.image_file_id as image FROM attachments...
```

**راه‌حل:**
- برای `InlineQueryResultArticle`، پارامتر `thumbnail_url` **نمی‌تواند** از `file_id` استفاده کند؛ باید URL واقعی (http/https) باشد
- **گزینه 1:** از `InlineQueryResultPhoto` به جای `Article` استفاده شود و `photo_file_id` داده شود
- **گزینه 2:** تصاویر را در یک CDN/سرور host کنیم و URL بدهیم
- **گزینه 3 (توصیه شده):** برای نتایج Inline از `Article` بدون thumbnail استفاده شود (فقط متن و دکمه‌ها)

**اصلاح سند:**
- بخش 4، زیربخش "انواع نتیجه" را تغییر دهید:
  ```markdown
  - `InlineQueryResultArticle` برای اقلام متنی با `InputTextMessageContent`
  - **نکته مهم:** چون تصاویر به صورت `file_id` ذخیره می‌شوند و `thumbnail_url` نیاز به URL دارد، از thumbnail استفاده **نمی‌کنیم** مگر اینکه تصاویر را در CDN host کنیم
  - **جایگزین:** استفاده از `InlineQueryResultCachedPhoto` برای نتایج دارای تصویر (با `photo_file_id`)
  ```

### 2. **محدودیت InlineQueryResultCachedPhoto**
اگر بخواهیم از `InlineQueryResultCachedPhoto` استفاده کنیم:
- نیاز به `photo_file_id` (تأیید ✅)
- **محدودیت:** `input_message_content` برای cached results معمولاً caption پیش‌فرض را override نمی‌کند
- پیام ارسالی شامل عکس + caption خواهد بود، اما دکمه‌های inline (`reply_markup`) کار می‌کنند

**پیشنهاد نهایی:**
ترکیبی از هر دو:
- برای اتچمنت‌های دارای عکس: `InlineQueryResultCachedPhoto` با `reply_markup`
- برای پیشنهادهای اقدام (برترهای فصل، تنظیمات): `InlineQueryResultArticle` بدون thumbnail

### 3. **مدیریت /start با پارامتر**
**واقعیت کد:** هندلر `/start` فعلی در `MainMenuHandler.start()` پارامترها را handle نمی‌کند.

**نیاز:** اضافه کردن منطق برای:
```python
async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    # بررسی context.args برای deep-link
    if context.args and len(context.args) > 0:
        param = context.args[0]
        if param == "inline":
            # نمایش منوی ویژه اینلاین یا راهنمایی
            ...
        # سایر پارامترها...
    else:
        # منوی عادی
        ...
```

**اصلاح سند:**
- بخش 11 (نقشه پیاده‌سازی)، اضافه کردن مرحله:
  ```markdown
  7. اصلاح `MainMenuHandler.start()` برای handle کردن `context.args` و deep-link parameters
  ```

### 4. **Feature Flag برای Inline Mode**
**توصیه اضافی:** اضافه کردن متغیر محیطی:
```python
# .env
INLINE_MODE_ENABLED=false  # default
```

و در `app/registry/inline_registry.py`:
```python
import os
INLINE_ENABLED = os.getenv('INLINE_MODE_ENABLED', 'false').lower() == 'true'

def register(self):
    if not INLINE_ENABLED:
        logger.info("Inline mode is disabled via INLINE_MODE_ENABLED flag")
        return
    # ... ثبت handlers
```

### 5. **سازگاری Callback در پیام‌های اینلاین**
- در پیام‌های اینلاین ممکن است `CallbackQuery.message` مقدار `None` داشته باشد و فقط `CallbackQuery.inline_message_id` موجود باشد.
- برای ویرایش پیام، از wrapperهای `query.edit_message_caption()` و `query.edit_message_reply_markup()` استفاده کنید که روی پیام‌های اینلاین نیز کار می‌کنند.
- هر جایی که به `query.message.caption` یا `query.message.reply_markup` تکیه شده، guard بگذارید و در صورت نبود پیام:
  - caption را از منبع امن (DB/متن تولیدی) تهیه کنید
  - کیبورد را با `build_feedback_buttons()` بازسازی کنید
- دکمه‌های `att_copy_…`، `att_like_…`، `att_dislike_…`، `att_fb_…` باید بدون وابستگی به `query.message` هم درست عمل کنند.

### 6. **عدم استفاده از require_channel_membership در هندلرهای اینلاین**
- به‌دلیل ماهیت Inline، چک عضویت کانال نباید مانع پاسخ‌دهی به inline query در گروه‌ها شود.
- محدودیت دسترسی (عضویت اجباری) را در زمان Switch to PM (دکمه `InlineQueryResultsButton`) یا هنگام نمایش منوها در پی‌وی enforce کنید.

---

## 🔧 پیشنهادات بهبود سند

### بخش 4 - ساختار داده
**افزودن:**
```markdown
### 4.1) محدودیت تصاویر و راه‌حل
- **مشکل:** دیتابیس فقط `image_file_id` دارد، نه URL
- **راه‌حل:** استفاده از `InlineQueryResultCachedPhoto` برای نتایج دارای تصویر:
  ```python
  InlineQueryResultCachedPhoto(
      id=str(attachment_id),
      photo_file_id=attachment['image'],
      title=f"{att_name} - {weapon}",
      description=f"کد: {code} | {mode_name}",
      reply_markup=InlineKeyboardMarkup([...])
  )
  ```
- برای اقدام‌های بدون تصویر (برترهای فصل، تنظیمات): `InlineQueryResultArticle`
```

### بخش 5.2 - اسکلت کد
**اصلاح:**
```python
def build_attachment_results(items):
    """ساخت نتایج اتچمنت با تصویر"""
    results = []
    for item in items:
        # اگر tuple است (PostgreSQL format)
        if isinstance(item, tuple):
            category, weapon, mode, attachment = item
        else:
            attachment = item['attachment']
            weapon = item['weapon']
            mode = item['mode']
        
        att_id = attachment.get('id')
        if not att_id:
            continue
        
        # ساخت دکمه‌ها
        keyboard = [[
            InlineKeyboardButton("📋 کپی کد", callback_data=f"att_copy_{att_id}"),
            InlineKeyboardButton("💬 ثبت نظر", callback_data=f"att_fb_{att_id}")
        ]]
        
        # استفاده از CachedPhoto برای نتایج دارای تصویر
        if attachment.get('image'):
            results.append(InlineQueryResultCachedPhoto(
                id=f"att-{att_id}-{mode}",
                photo_file_id=attachment['image'],
                title=f"{attachment['name']} - {weapon}",
                description=f"کد: {attachment['code']} | {GAME_MODES[mode]}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            ))
        else:
            # اگر تصویر نداشت، Article استفاده کن
            results.append(InlineQueryResultArticle(
                id=f"att-{att_id}-{mode}",
                title=f"{attachment['name']} - {weapon}",
                input_message_content=InputTextMessageContent(
                    message_text=f"**{attachment['name']}**\nکد: `{attachment['code']}`\n{weapon} | {GAME_MODES[mode]}"
                ),
                description=f"کد: {attachment['code']}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            ))
    
    return results
```

### بخش 13 - FAQ
**افزودن:**
```markdown
- **آیا می‌توانیم file_id را به جای URL در thumbnail_url استفاده کنیم?** خیر، `thumbnail_url` باید URL واقعی (http/https) باشد. برای استفاده از file_id از `InlineQueryResultCachedPhoto` استفاده کنید.
```

---

## 📋 چک‌لیست اصلاحات ضروری سند

- [ ] بخش 4: اصلاح توضیح تصاویر و افزودن `InlineQueryResultCachedPhoto`
- [ ] بخش 5.1: اضافه کردن import برای `InlineQueryResultCachedPhoto`
- [ ] بخش 5.2: بازنویسی `build_attachment_results()` با استفاده از `CachedPhoto`
- [ ] بخش 11: اضافه کردن مرحله "اصلاح start handler برای deep-link"
- [ ] بخش 10: اضافه کردن Feature Flag (`INLINE_MODE_ENABLED`)
- [ ] بخش 13: افزودن FAQ درباره file_id vs URL

---

## 🎯 نتیجه‌گیری

**وضعیت کلی سند:** ✅ **عالی و قابل پیاده‌سازی** با چند اصلاح جزئی

**نکات کلیدی:**
1. معماری پیشنهادی کاملاً سازگار با ساختار فعلی پروژه است
2. تمام API های PTB v21.5 صحیح هستند
3. تنها تغییر اساسی: استفاده از `InlineQueryResultCachedPhoto` به جای `Article` با `thumb_url`
4. نیاز به handle کردن deep-link در start handler

**آماده برای پیاده‌سازی:** پس از اعمال اصلاحات بالا، سند کاملاً دقیق و قابل اجرا خواهد بود.

---

## 📝 نمونه کد نهایی پیشنهادی

```python
# handlers/inline/inline_handler.py
from telegram import (
    Update, 
    InlineQueryResultArticle, 
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultsButton
)
from telegram.ext import ContextTypes
from config.config import GAME_MODES
from handlers.user.base_user_handler import BaseUserHandler

class InlineHandler(BaseUserHandler):
    """مدیریت Inline Queries"""
    
    async def handle_inline_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """پردازش inline query"""
        q = (update.inline_query.query or "").strip()
        user_id = update.effective_user.id if update.effective_user else None
        
        results = []
        
        if len(q) < 2:
            # Zero-Query: پیشنهادها
            results = self._build_suggestions()
        else:
            # جستجو در اتچمنت‌ها
            db_results = self.db.search(q)
            results = self._build_attachment_results(db_results)
            
            # ثبت جستجو
            if user_id:
                self.db.track_search(user_id, q, len(results), 0)
        
        # محدود کردن به 25 نتیجه
        results = results[:25]
        
        # دکمه Switch to PM
        button = InlineQueryResultsButton(
            text="🔔 باز کردن ربات",
            start_parameter="inline"
        )
        
        await update.inline_query.answer(
            results=results,
            is_personal=True,
            cache_time=2,
            button=button
        )
    
    def _build_attachment_results(self, items):
        """ساخت نتایج اتچمنت"""
        results = []
        
        for item in items[:25]:
            # Parse format
            if isinstance(item, tuple):
                category, weapon, mode, attachment = item
            else:
                attachment = item['attachment']
                weapon = item['weapon']
                mode = item['mode']
            
            att_id = attachment.get('id')
            if not att_id:
                continue
            
            # دکمه‌ها
            keyboard = [[
                InlineKeyboardButton("📋 کپی کد", callback_data=f"att_copy_{att_id}"),
                InlineKeyboardButton("💬 ثبت نظر", callback_data=f"att_fb_{att_id}")
            ]]
            
            mode_name = GAME_MODES.get(mode, mode)
            
            # استفاده از CachedPhoto
            if attachment.get('image'):
                results.append(InlineQueryResultCachedPhoto(
                    id=f"att-{att_id}-{mode}",
                    photo_file_id=attachment['image'],
                    title=f"{attachment['name']} ({weapon})",
                    description=f"کد: {attachment['code']} | {mode_name}",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    caption=f"**{attachment['name']}**\nکد: `{attachment['code']}`\n{weapon} | {mode_name}",
                    parse_mode='Markdown'
                ))
        
        return results
    
    def _build_suggestions(self):
        """ساخت پیشنهادهای Zero-Query"""
        return [
            InlineQueryResultArticle(
                id="suggestion-top-br",
                title="⭐ برترهای فصل (بتل رویال)",
                input_message_content=InputTextMessageContent(
                    "برای مشاهده برترین اتچمنت‌های فصل، از منوی ربات استفاده کنید."
                ),
                description="مشاهده برترین‌های BR",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📱 باز کردن ربات", url="t.me/YourBot?start=season_top_br")
                ]])
            ),
            # ... سایر پیشنهادها
        ]
    
    async def handle_chosen_inline_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ثبت انتخاب نتیجه برای آنالیتیکس"""
        result_id = update.chosen_inline_result.result_id
        user_id = update.effective_user.id if update.effective_user else None
        
        # Parse result_id (مثلاً: "att-123-br")
        if result_id.startswith("att-"):
            parts = result_id.split("-")
            if len(parts) >= 2:
                att_id = int(parts[1])
                # ثبت view
                if user_id:
                    self.db.track_attachment_view(user_id, att_id)
```
