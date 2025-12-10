# مشخصات API مینی‌اپ تلگرام CODM Attachments

این سند طراحی پیشنهادی API HTTP/JSON برای مینی‌اپ را بر اساس کد فعلی دیتابیس و آنالیتیکس توضیح می‌دهد. این API هنوز پیاده‌سازی نشده و نقش «قرارداد» بین Frontend مینی‌اپ و Backend را دارد.

---

## ۱. اصول کلی طراحی

- **Base URL** (نمونه):
  - `https://your-domain.com/miniapp/v1`
- **فرمت پاسخ:**

```json
{
  "ok": true,
  "result": {...},
  "error": null
}
```

- در صورت خطا:

```json
{
  "ok": false,
  "result": null,
  "error": {
    "code": "BAD_REQUEST",
    "message": "پارامتر category نامعتبر است"
  }
}
```

- **احراز هویت:**
  - هر درخواست باید `initData` معتبر تلگرام را ارائه کند.
  - پیشنهاد: اولین درخواست، `initData` را ارسال و در پاسخ یک `session_token` کوتاه‌عمر دریافت کند؛ درخواست‌های بعدی فقط `session_token` را در هدر می‌فرستند.

---

## ۲. احراز هویت و Session

### ۲.۱. POST /auth/verify

- **مسیر:** `POST /miniapp/v1/auth/verify`
- **ورودی:**

```json
{
  "init_data": "<raw initData string from Telegram WebApp>"
}
```

- **پردازش (در Backend):**
  - اعتبارسنجی `init_data` طبق الگوریتم رسمی تلگرام (شرح در `SECURITY.md`).
  - استخراج `user.id`, `user.language_code` و سایر فیلدهای مفید.
  - ثبت/به‌روزرسانی کاربر در DB از طریق `DatabaseAdapter.upsert_user` و `set_user_language`.
  - ساخت یک `session_token` کوتاه‌عمر (مثلاً JWT یا رشته تصادفی).

- **خروجی نمونه:**

```json
{
  "ok": true,
  "result": {
    "session_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "user": {
      "id": 123456789,
      "language": "fa",
      "username": "player123"
    },
    "config": {
      "default_mode": "br",
      "supported_modes": ["br", "mp"],
      "supported_langs": ["fa", "en"]
    }
  },
  "error": null
}
```

---

## ۳. متادیتا و تنظیمات

### ۳.1. GET /meta

- **مسیر:** `GET /miniapp/v1/meta`
- **Headers:**
  - `Authorization: Bearer <session_token>`
- **خروجی:** اطلاعات پایه برای UI:

```json
{
  "ok": true,
  "result": {
    "modes": [
      {"key": "br", "label": "Battle Royale"},
      {"key": "mp", "label": "Multiplayer"}
    ],
    "categories": [
      {"key": "assault_rifle", "name": "Assault Rifle"},
      {"key": "smg", "name": "SMG"}
    ]
  },
  "error": null
}
```

> منبع داده: ثابت‌های `WEAPON_CATEGORIES` در `config.config` یا جدول `weapon_categories`.

---

## ۴. دسته‌ها و سلاح‌ها

### ۴.۱. GET /categories

- **مسیر:** `GET /miniapp/v1/categories`
- **خروجی:**

```json
{
  "ok": true,
  "result": [
    {"key": "assault_rifle", "name": "Assault Rifle"},
    {"key": "smg", "name": "SMG"},
    {"key": "sniper", "name": "Sniper"}
  ],
  "error": null
}
```

- **پیاده‌سازی پیشنهادی:**
  - استفاده از `WEAPON_CATEGORIES` یا `DatabaseAdapter.get_all_category_counts` برای برگشت دادن تعداد نیز (در صورت نیاز).

### ۴.۲. GET /weapons

- **مسیر:** `GET /miniapp/v1/weapons`
- **پارامترها:**
  - `category` (الزامی) – مانند `assault_rifle`.
  - `page`, `page_size` (اختیاری) – برای pagination ساده.

- **خروجی:**

```json
{
  "ok": true,
  "result": {
    "items": [
      {"name": "AK-47", "category": "assault_rifle"},
      {"name": "M13", "category": "assault_rifle"}
    ],
    "page": 1,
    "page_size": 50,
    "total": 10
  },
  "error": null
}
```

- **منبع داده:**
  - `DatabaseAdapter.get_weapons_in_category(category)`.

---

## ۵. اتچمنت‌ها

### ۵.۱. GET /attachments

- **مسیر:** `GET /miniapp/v1/attachments`
- **پارامترها:**
  - `category` (الزامی)
  - `weapon` (الزامی)
  - `mode` (اختیاری، پیش‌فرض `br`)

- **خروجی:** ترکیب top/all/season_top بر اساس متدهای دیتابیس موجود:

```json
{
  "ok": true,
  "result": {
    "category": "assault_rifle",
    "weapon": "AK-47",
    "mode": "br",
    "top": [
      {
        "id": 101,
        "code": "AK47-BR-TOP1",
        "name": "Aggressive Build",
        "image": "<file_id>",
        "season_top": false,
        "stats": {
          "views": 1200,
          "clicks": 450,
          "rating": 4.7
        }
      }
    ],
    "all": [
      {
        "id": 102,
        "code": "AK47-BR-ALL1",
        "name": "Balanced Build",
        "image": null,
        "top": false,
        "season_top": false
      }
    ],
    "season_top": [
      {
        "id": 201,
        "code": "AK47-BR-S1",
        "name": "Season 1 Top",
        "image": "<file_id>",
        "season_top": true
      }
    ]
  },
  "error": null
}
```

- **منبع داده:**
  - `DatabaseAdapter.get_top_attachments(category, weapon, mode)`
  - `DatabaseAdapter.get_all_attachments(category, weapon, mode)`
  - `DatabaseAdapter.get_season_top_attachments_for_weapon(category, weapon, mode)`
  - داده‌های آماری از جداول `attachments`, `attachment_performance`, `user_attachment_engagement` (در صورت نیاز).

---

## ۶. ترندها و پیشنهادها

### ۶.۱. GET /trending

- **مسیر:** `GET /miniapp/v1/trending`
- **پارامترها:**
  - `limit` (اختیاری، پیش‌فرض ۱۰، حداکثر ۱۰۰)

- **خروجی نمونه:**

```json
{
  "ok": true,
  "result": [
    {
      "id": 301,
      "name": "AK117 Aggro",
      "code": "AK117-BR-TREND1",
      "weapon": "AK117",
      "category": "assault_rifle",
      "trending_score": 82.5,
      "popularity_score": 91.3,
      "total_views": 3500
    }
  ],
  "error": null
}
```

- **منبع داده:**
  - `AttachmentAnalytics.get_trending_attachments(limit)`.

### ۶.۲. GET /search

- **مسیر:** `GET /miniapp/v1/search`
- **پارامترها:**
  - `q` (متن جستجو، الزامی)
  - `limit` (اختیاری)

- **خروجی:**

```json
{
  "ok": true,
  "result": [
    {
      "category": "assault_rifle",
      "weapon": "AK-47",
      "mode": "br",
      "attachment": {
        "id": 401,
        "code": "AK47-BR-TOP1",
        "name": "Aggressive Build",
        "image": "<file_id>",
        "top": true,
        "season_top": false
      }
    }
  ],
  "error": null
}
```

- **منبع داده:**
  - `DatabaseAdapter.search_attachments_fts(query, limit)` (در صورت موجود بودن)
  - یا `DatabaseAdapter.search_attachments(query)` به‌عنوان fallback.

---

## ۷. رویدادهای کاربر (Analytics Events)

### ۷.۱. POST /events

- **مسیر:** `POST /miniapp/v1/events`
- **Headers:**
  - `Authorization: Bearer <session_token>`

- **ورودی:**

```json
{
  "attachment_id": 101,
  "event_type": "view",       
  "metadata": {
    "source": "miniapp_home"
  }
}
```

- **مقادیر مجاز `event_type`:**
  - `view`, `click`, `share`, `copy`, `rate`

- **رفتار در Backend:**
  - `view` → `AttachmentAnalytics.track_view`
  - `click` → `AttachmentAnalytics.track_click`
  - `share` → `AttachmentAnalytics.track_share`
  - `copy` → `AttachmentAnalytics.track_copy`
  - `rate` → اگر `metadata.rating` وجود داشته باشد، `AttachmentAnalytics.track_rating`

- **خروجی نمونه:**

```json
{
  "ok": true,
  "result": {"status": "recorded"},
  "error": null
}
```

- **نکات امنیتی:**
  - باید روی این endpoint، rate limiting پیاده شود.
  - `attachment_id` باید در DB موجود باشد؛ در غیر این صورت، خطای `404` برگشت داده شود.

---

## ۸. کدهای خطا و قراردادها

### ۸.۱. ساختار کلی خطا

```json
{
  "ok": false,
  "result": null,
  "error": {
    "code": "UNAUTHORIZED",
    "message": "session_token نامعتبر است"
  }
}
```

### ۸.۲. کدهای متداول

- `BAD_REQUEST` – پارامترهای ورودی نامعتبر.
- `UNAUTHORIZED` – session یا initData نامعتبر.
- `NOT_FOUND` – منبعی مثل سلاح یا اتچمنت یافت نشد.
- `RATE_LIMITED` – تجاوز از حد مجاز درخواست.
- `INTERNAL_ERROR` – خطای پیش‌بینی‌نشده سمت سرور.

---

## ۹. نسخه‌بندی و توسعه آینده

- تمام مسیرهای فعلی تحت `/miniapp/v1` تعریف می‌شوند.
- در صورت نیاز به تغییرات ناسازگار، نسخه‌ی جدیدی مثل `/miniapp/v2` تعریف می‌شود، بدون شکستن سازگاری مینی‌اپ‌های قدیمی.

این سند به‌عنوان قرارداد رسمی بین Frontend و Backend مینی‌اپ استفاده می‌شود و باید در زمان پیاده‌سازی واقعی، با وضعیت نهایی کد هماهنگ و به‌روزرسانی شود.
