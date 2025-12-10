# راهنمای پیاده‌سازی قابلیت‌های جدید

راهنمای مرحله‌به‌مرحله پیاده‌سازی 4 قابلیت کلیدی بدون تخریب ساختار پروژه

---

## 📋 فهرست

1. [Webhook Mode](#1-webhook-mode)
2. [Advanced Analytics](#2-advanced-analytics)
3. [Social Features](#3-social-features)
4. [CMS System](#4-cms-system)

---

## 1. Webhook Mode

### مراحل پیاده‌سازی

#### 1.1 ساخت فایل‌های جدید

**`core/webhook/__init__.py`**
```python
# خالی
```

**`core/webhook/webhook_server.py`** (200 خط کد کامل)

```python
from flask import Flask, request, jsonify
from telegram import Update
import asyncio, logging

logger = logging.getLogger(__name__)

class WebhookServer:
    def __init__(self, application, webhook_path="/webhook"):
        self.app = Flask(__name__)
        self.application = application
        self.webhook_path = webhook_path
        self._setup_routes()
    
    def _setup_routes(self):
        @self.app.route('/health', methods=['GET'])
        def health():
            return jsonify({'status': 'healthy'})
        
        @self.app.route(self.webhook_path, methods=['POST'])
        def webhook():
            try:
                update = Update.de_json(request.get_json(force=True), self.application.bot)
                asyncio.run(self.application.process_update(update))
                return jsonify({'status': 'ok'}), 200
            except Exception as e:
                logger.error(f"Webhook error: {e}")
                return jsonify({'status': 'error'}), 500
    
    def run(self, host='0.0.0.0', port=8443, ssl_context=None):
        self.app.run(host=host, port=port, ssl_context=ssl_context, threaded=True)
```

#### 1.2 تنظیمات

**فایل `.env`** - اضافه کردن:
```bash
USE_WEBHOOK=false  # true برای فعال‌سازی
WEBHOOK_URL=https://yourdomain.com
WEBHOOK_PORT=8443
WEBHOOK_PATH=/webhook
SSL_CERT_PATH=/path/to/cert.pem
SSL_KEY_PATH=/path/to/privkey.pem
```

**فایل `config/config.py`** - اضافه کردن:
```python
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "false").lower() == "true"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8443"))
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")
SSL_CERT_PATH = os.getenv("SSL_CERT_PATH")
SSL_KEY_PATH = os.getenv("SSL_KEY_PATH")
```

#### 1.3 تغییر main.py

**در کلاس `CODMAttachmentsBot`** - جایگزین کردن متد `run()`:

```python
def run(self):
    from config.config import USE_WEBHOOK
    logger.info("Starting bot...")
    self.setup_signal_handlers()
    
    from telegram.ext import ApplicationBuilder
    self.application = (ApplicationBuilder()
        .token(BOT_TOKEN).post_init(self.post_init)
        .post_shutdown(self.post_shutdown).build())
    
    self.application.bot_data['database'] = self.db
    self.application.bot_data['admins'] = ADMIN_IDS
    self.setup_handlers()
    
    try:
        if USE_WEBHOOK:
            self._run_webhook()
        else:
            self._run_polling()
    except KeyboardInterrupt:
        logger.info("Stopped")
    finally:
        loop = asyncio.get_event_loop()
        if not self.is_shutting_down:
            loop.run_until_complete(self.cleanup())

def _run_polling(self):
    self.application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

def _run_webhook(self):
    import ssl
    from config.config import *
    from core.webhook.webhook_server import WebhookServer
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def setup():
        await self.application.bot.set_webhook(
            url=f"{WEBHOOK_URL}:{WEBHOOK_PORT}{WEBHOOK_PATH}",
            drop_pending_updates=True
        )
    loop.run_until_complete(setup())
    
    ssl_ctx = None
    if SSL_CERT_PATH and SSL_KEY_PATH:
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(SSL_CERT_PATH, SSL_KEY_PATH)
    
    server = WebhookServer(self.application, WEBHOOK_PATH)
    server.run(port=WEBHOOK_PORT, ssl_context=ssl_ctx)
```

#### 1.4 SSL Setup

```bash
# نصب certbot
sudo apt install certbot

# دریافت certificate
sudo certbot certonly --standalone -d yourdomain.com

# مسیر فایل‌ها:
# /etc/letsencrypt/live/yourdomain.com/fullchain.pem
# /etc/letsencrypt/live/yourdomain.com/privkey.pem
```

---

## 2. Advanced Analytics

### مراحل پیاده‌سازی

#### 2.1 Schema دیتابیس

**فایل `scripts/analytics_schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS analytics_events (
    event_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT,
    event_type TEXT NOT NULL,
    event_category TEXT NOT NULL,
    event_data JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX ON analytics_events(user_id);
CREATE INDEX ON analytics_events(event_type);
CREATE INDEX ON analytics_events(created_at);

CREATE TABLE IF NOT EXISTS user_analytics (
    user_id BIGINT PRIMARY KEY,
    first_seen TIMESTAMP DEFAULT NOW(),
    last_seen TIMESTAMP DEFAULT NOW(),
    total_actions INTEGER DEFAULT 0,
    total_searches INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS daily_metrics (
    metric_date DATE PRIMARY KEY,
    new_users INTEGER DEFAULT 0,
    active_users INTEGER DEFAULT 0,
    total_searches INTEGER DEFAULT 0,
    avg_response_time DECIMAL(10,2) DEFAULT 0
);
```

**اجرا**:
```bash
psql -U username -d database_name -f scripts/analytics_schema.sql
```

#### 2.2 Event Tracker

**فایل `core/analytics/__init__.py`**:
```python
# خالی
```

**فایل `core/analytics/event_tracker.py`**:

```python
from datetime import datetime
from typing import Optional, Dict
from collections import deque
import logging, json

logger = logging.getLogger(__name__)

class EventTracker:
    def __init__(self, db, buffer_size=100):
        self.db = db
        self.buffer = deque(maxlen=buffer_size * 2)
        self.buffer_size = buffer_size
    
    async def track(self, user_id: Optional[int], event_type: str, 
                   category: str, data: Dict = None):
        event = {
            'user_id': user_id,
            'event_type': event_type,
            'event_category': category,
            'event_data': json.dumps(data or {}),
            'created_at': datetime.now()
        }
        self.buffer.append(event)
        
        if len(self.buffer) >= self.buffer_size:
            await self.flush()
    
    async def flush(self):
        if not self.buffer:
            return
        events = list(self.buffer)
        self.buffer.clear()
        
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                for e in events:
                    cur.execute("""
                        INSERT INTO analytics_events 
                        (user_id, event_type, event_category, event_data, created_at)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (e['user_id'], e['event_type'], e['event_category'], 
                          e['event_data'], e['created_at']))
                conn.commit()
        except Exception as ex:
            logger.error(f"Flush error: {ex}")
```

#### 2.3 Analytics Engine

**فایل `core/analytics/analytics_engine.py`**:

```python
from datetime import datetime, timedelta
from typing import Dict, List

class AnalyticsEngine:
    def __init__(self, db):
        self.db = db
    
    def get_user_retention(self, days=7) -> Dict:
        """نرخ بازگشت کاربران"""
        query = """
        WITH cohort AS (
            SELECT user_id, DATE(first_seen) as cohort_date
            FROM user_analytics
            WHERE first_seen >= NOW() - INTERVAL '%s days'
        )
        SELECT cohort_date, 
               COUNT(DISTINCT c.user_id) as total_users,
               COUNT(DISTINCT CASE WHEN last_seen > first_seen + INTERVAL '1 day' 
                     THEN c.user_id END) as returned_users,
               ROUND(100.0 * COUNT(DISTINCT CASE WHEN last_seen > first_seen + INTERVAL '1 day' 
                     THEN c.user_id END) / COUNT(DISTINCT c.user_id), 2) as retention_rate
        FROM cohort c
        JOIN user_analytics ua ON c.user_id = ua.user_id
        GROUP BY cohort_date ORDER BY cohort_date DESC
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (days,))
            return [{'date': row[0], 'total': row[1], 'returned': row[2], 
                    'rate': float(row[3])} for row in cur.fetchall()]
    
    def get_popular_searches(self, days=7, limit=20) -> List[Dict]:
        """محبوب‌ترین جستجوها"""
        query = """
        SELECT event_data->>'query' as query, COUNT(*) as count
        FROM analytics_events
        WHERE event_type = 'search_query' 
              AND created_at >= NOW() - INTERVAL '%s days'
              AND event_data->>'query' IS NOT NULL
        GROUP BY query ORDER BY count DESC LIMIT %s
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (days, limit))
            return [{'query': row[0], 'count': row[1]} for row in cur.fetchall()]
    
    def get_daily_stats(self, days=30) -> List[Dict]:
        """آمار روزانه"""
        query = """
        SELECT metric_date, new_users, active_users, total_searches
        FROM daily_metrics
        WHERE metric_date >= NOW() - INTERVAL '%s days'
        ORDER BY metric_date DESC
        """
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, (days,))
            return [{'date': row[0], 'new': row[1], 'active': row[2], 
                    'searches': row[3]} for row in cur.fetchall()]
```

#### 2.4 Admin Handler برای Dashboard

**فایل `handlers/admin/modules/analytics/analytics_dashboard.py`** - اضافه کردن:

```python
from core.analytics.analytics_engine import AnalyticsEngine

async def show_analytics_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = context.bot_data['database']
    engine = AnalyticsEngine(db)
    
    # دریافت آمار
    retention = engine.get_user_retention(days=7)
    popular = engine.get_popular_searches(days=7, limit=10)
    daily = engine.get_daily_stats(days=7)
    
    # ساخت پیام
    text = "📊 **داشبورد آنالیتیکس**\n\n"
    
    # Retention
    if retention:
        last = retention[0]
        text += f"🔄 **بازگشت کاربران (7 روز)**\n"
        text += f"   • نرخ بازگشت: {last['rate']}%\n"
        text += f"   • برگشته: {last['returned']}/{last['total']}\n\n"
    
    # Popular Searches
    text += "🔍 **محبوب‌ترین جستجوها**\n"
    for i, s in enumerate(popular[:5], 1):
        text += f"   {i}. {s['query']} ({s['count']})\n"
    
    # Daily Stats
    if daily:
        text += f"\n📈 **آمار امروز**\n"
        text += f"   • کاربران جدید: {daily[0]['new']}\n"
        text += f"   • کاربران فعال: {daily[0]['active']}\n"
        text += f"   • جستجوها: {daily[0]['searches']}\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')
```

#### 2.5 Tracking در Handlers

**مثال - در `handlers/user/modules/search/search_handler.py`**:

```python
from core.analytics.event_tracker import EventTracker

class SearchHandler(BaseUserHandler):
    def __init__(self, db):
        super().__init__(db)
        self.tracker = EventTracker(db)
    
    async def search_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.message.text
        user_id = update.effective_user.id
        
        # Track search event
        await self.tracker.track(
            user_id=user_id,
            event_type='search_query',
            category='search',
            data={'query': query, 'timestamp': datetime.now().isoformat()}
        )
        
        # ادامه کد search موجود...
```

---

## 3. Social Features

### مراحل پیاده‌سازی

#### 3.1 Schema

**فایل `scripts/social_schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id BIGINT PRIMARY KEY,
    display_name TEXT,
    bio TEXT,
    level INTEGER DEFAULT 1,
    points INTEGER DEFAULT 0,
    badges JSONB DEFAULT '[]'::jsonb,
    is_public BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_follows (
    follower_id BIGINT,
    following_id BIGINT,
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (follower_id, following_id)
);

CREATE TABLE IF NOT EXISTS leaderboard (
    user_id BIGINT PRIMARY KEY,
    total_contributions INTEGER DEFAULT 0,
    total_likes_received INTEGER DEFAULT 0,
    rank INTEGER,
    last_updated TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS achievements (
    achievement_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    icon TEXT,
    points INTEGER DEFAULT 0,
    criteria JSONB
);

CREATE TABLE IF NOT EXISTS user_achievements (
    user_id BIGINT,
    achievement_id INTEGER,
    earned_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, achievement_id),
    FOREIGN KEY (achievement_id) REFERENCES achievements(achievement_id)
);
```

#### 3.2 Social Manager

**فایل `managers/social_manager.py`**:

```python
from typing import List, Dict, Optional

class SocialManager:
    def __init__(self, db):
        self.db = db
    
    def follow_user(self, follower_id: int, following_id: int) -> bool:
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO user_follows (follower_id, following_id)
                    VALUES (%s, %s) ON CONFLICT DO NOTHING
                """, (follower_id, following_id))
                conn.commit()
                return True
        except:
            return False
    
    def unfollow_user(self, follower_id: int, following_id: int) -> bool:
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("""
                    DELETE FROM user_follows 
                    WHERE follower_id = %s AND following_id = %s
                """, (follower_id, following_id))
                conn.commit()
                return True
        except:
            return False
    
    def get_leaderboard(self, limit: int = 50) -> List[Dict]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT user_id, total_contributions, total_likes_received, rank
                FROM leaderboard
                ORDER BY rank ASC LIMIT %s
            """, (limit,))
            return [{'user_id': r[0], 'contributions': r[1], 
                    'likes': r[2], 'rank': r[3]} for r in cur.fetchall()]
    
    def add_points(self, user_id: int, points: int):
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE user_profiles SET points = points + %s 
                WHERE user_id = %s
            """, (points, user_id))
            conn.commit()
    
    def grant_achievement(self, user_id: int, achievement_id: int):
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_achievements (user_id, achievement_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING
            """, (user_id, achievement_id))
            conn.commit()
```

#### 3.3 User Profile Handler

**فایل `handlers/user/modules/social/profile_handler.py`**:

```python
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db = context.bot_data['database']
    
    # دریافت اطلاعات
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT display_name, bio, level, points, badges
            FROM user_profiles WHERE user_id = %s
        """, (user_id,))
        row = cur.fetchone()
    
    if not row:
        text = "❌ پروفایل یافت نشد"
    else:
        text = f"👤 **پروفایل شما**\n\n"
        text += f"🎭 نام: {row[0] or 'بدون نام'}\n"
        text += f"📝 بیو: {row[1] or 'ندارد'}\n"
        text += f"⭐ سطح: {row[2]}\n"
        text += f"💎 امتیاز: {row[3]}\n"
    
    keyboard = [[InlineKeyboardButton("✏️ ویرایش پروفایل", callback_data="edit_profile")]]
    await update.message.reply_text(text, parse_mode='Markdown', 
                                    reply_markup=InlineKeyboardMarkup(keyboard))
```

---

## 4. CMS System

### مراحل پیاده‌سازی

#### 4.1 Schema

**فایل `scripts/cms_schema.sql`**:

```sql
CREATE TABLE IF NOT EXISTS cms_content (
    content_id SERIAL PRIMARY KEY,
    content_type TEXT NOT NULL,  -- 'news', 'tutorial', 'meta_report', 'event'
    title TEXT NOT NULL,
    body TEXT,
    media JSONB DEFAULT '[]'::jsonb,
    tags TEXT[] DEFAULT '{}',
    author_id BIGINT,
    status TEXT DEFAULT 'draft',  -- 'draft', 'published', 'archived'
    published_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX ON cms_content(content_type);
CREATE INDEX ON cms_content(status);
CREATE INDEX ON cms_content(published_at);

CREATE TABLE IF NOT EXISTS cms_categories (
    category_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    icon TEXT
);

CREATE TABLE IF NOT EXISTS cms_content_categories (
    content_id INTEGER,
    category_id INTEGER,
    PRIMARY KEY (content_id, category_id)
);
```

#### 4.2 CMS Manager

**فایل `managers/cms_manager.py`**:

```python
from datetime import datetime
from typing import List, Dict, Optional

class CMSManager:
    def __init__(self, db):
        self.db = db
    
    def create_content(self, content_type: str, title: str, body: str,
                      author_id: int, tags: List[str] = None) -> Optional[int]:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO cms_content (content_type, title, body, author_id, tags)
                VALUES (%s, %s, %s, %s, %s) RETURNING content_id
            """, (content_type, title, body, author_id, tags or []))
            conn.commit()
            return cur.fetchone()[0]
    
    def publish_content(self, content_id: int) -> bool:
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE cms_content 
                SET status = 'published', published_at = NOW()
                WHERE content_id = %s
            """, (content_id,))
            conn.commit()
            return cur.rowcount > 0
    
    def get_published_content(self, content_type: str = None, 
                             limit: int = 10) -> List[Dict]:
        query = """
            SELECT content_id, content_type, title, body, tags, published_at
            FROM cms_content
            WHERE status = 'published'
        """
        params = []
        if content_type:
            query += " AND content_type = %s"
            params.append(content_type)
        query += " ORDER BY published_at DESC LIMIT %s"
        params.append(limit)
        
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            return [{'id': r[0], 'type': r[1], 'title': r[2], 
                    'body': r[3], 'tags': r[4], 'published': r[5]} 
                   for r in cur.fetchall()]
```

---

## ✅ Checklist کلی

### Webhook
- [ ] ساخت `core/webhook/`
- [ ] تنظیم `.env`
- [ ] تغییر `main.py`
- [ ] دریافت SSL
- [ ] تست

### Analytics
- [ ] اجرای schema
- [ ] ساخت `core/analytics/`
- [ ] افزودن tracking به handlers
- [ ] ساخت dashboard
- [ ] تست

### Social
- [ ] اجرای schema
- [ ] ساخت `managers/social_manager.py`
- [ ] ساخت handlers
- [ ] تست

### CMS
- [ ] اجرای schema
- [ ] ساخت `managers/cms_manager.py`
- [ ] ساخت admin handlers
- [ ] ساخت user handlers
- [ ] تست

---

**نکته مهم**: هر قابلیت رو به صورت تدریجی پیاده‌سازی کن و بعد از هر مرحله تست کن.
