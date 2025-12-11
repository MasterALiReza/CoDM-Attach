# راهنمای نصب کامل ربات CoDM Attachments

این راهنما مراحل نصب کامل ربات را از صفر توضیح می‌دهد.

## 📋 پیش‌نیازها

### سیستم عامل
- Ubuntu 20.04 LTS یا بالاتر (توصیه می‌شود)
- حداقل 2GB RAM
- حداقل 10GB فضای خالی

### نرم‌افزارهای مورد نیاز
- Python 3.10 یا بالاتر
- PostgreSQL 13 یا بالاتر
- Git
- دسترسی sudo

---

## 🚀 مراحل نصب

### مرحله 1️⃣: به‌روزرسانی سیستم

```bash
sudo apt update
sudo apt upgrade -y
```

### مرحله 2️⃣: نصب Python و وابستگی‌ها

```bash
sudo apt install -y python3 python3-pip python3-venv git
```

### مرحله 3️⃣: نصب و راه‌اندازی PostgreSQL

```bash
# نصب PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# شروع سرویس PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# بررسی وضعیت
sudo systemctl status postgresql
```

### مرحله 4️⃣: ایجاد دیتابیس و کاربر

```bash
# ورود به PostgreSQL
sudo -u postgres psql

# اجرای دستورات زیر در PostgreSQL:
```

```sql
-- ایجاد کاربر
CREATE USER codm_bot_user WITH PASSWORD 'CoDM_Secure_2025!@#';

-- ایجاد دیتابیس
CREATE DATABASE codm_bot OWNER codm_bot_user;

-- اعطای دسترسی‌ها
GRANT ALL PRIVILEGES ON DATABASE codm_bot TO codm_bot_user;
ALTER USER codm_bot_user CREATEDB;

-- خروج
\q
```

### مرحله 5️⃣: کلون کردن پروژه

```bash
# رفتن به مسیر /opt
cd /opt

# کلون کردن پروژه
sudo git clone https://github.com/MasterALiReza/CoDM-Attach.git codm-bot

# تغییر مالکیت پوشه
sudo chown -R $USER:$USER /opt/codm-bot

# ورود به پوشه پروژه
cd /opt/codm-bot
```

### مرحله 6️⃣: تنظیم محیط مجازی Python

```bash
# ایجاد محیط مجازی
python3 -m venv venv

# فعال‌سازی محیط مجازی
source venv/bin/activate

# نصب وابستگی‌ها
pip install --upgrade pip
pip install -r requirements.txt
```

### مرحله 7️⃣: راه‌اندازی دیتابیس

```bash
# اجرای اسکریپت راه‌اندازی دیتابیس
sudo -u postgres psql -d codm_bot -f scripts/setup_database.sql
```

### مرحله 8️⃣: تنظیمات محیطی

```bash
# کپی کردن فایل نمونه
cp .env.example .env

# ویرایش فایل .env
nano .env
```

**تنظیمات ضروری در `.env`:**

```env
# توکن ربات تلگرام (از @BotFather دریافت کنید)
BOT_TOKEN=YOUR_BOT_TOKEN_HERE

# آیدی عددی تلگرام شما (از @userinfobot دریافت کنید)
SUPER_ADMIN_ID=YOUR_TELEGRAM_USER_ID

# تنظیمات دیتابیس PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=codm_bot
POSTGRES_USER=codm_bot_user
POSTGRES_PASSWORD=CoDM_Secure_2025!@#

# URL کامل دیتابیس
DATABASE_URL=postgresql://codm_bot_user:CoDM_Secure_2025!@#@localhost:5432/codm_bot
```

💡 **نکات مهم:**
- `BOT_TOKEN` را از [@BotFather](https://t.me/BotFather) دریافت کنید
- `SUPER_ADMIN_ID` را از [@userinfobot](https://t.me/userinfobot) دریافت کنید
- رمز عبور دیتابیس را طبق نیاز خود تغییر دهید

### مرحله 9️⃣: اجرای اسکریپت نصب خودکار

```bash
# اجازه اجرا به اسکریپت
chmod +x deploy.sh

# اجرای اسکریپت (به صورت تعاملی)
./deploy.sh
```

اسکریپت از شما می‌پرسد:
1. توکن ربات
2. آیدی ادمین اصلی
3. تأیید برای ایجاد سرویس systemd

### مرحله 🔟: راه‌اندازی سرویس

```bash
# فعال‌سازی و شروع سرویس
sudo systemctl daemon-reload
sudo systemctl enable codm-bot
sudo systemctl start codm-bot

# بررسی وضعیت
sudo systemctl status codm-bot
```

### مرحله 1️⃣1️⃣: مشاهده لاگ‌ها

```bash
# مشاهده لاگ‌های زنده
sudo journalctl -u codm-bot -f

# مشاهده 100 خط آخر لاگ
sudo journalctl -u codm-bot -n 100
```

---

## ✅ تست عملکرد

1. **باز کردن ربات در تلگرام**
   ```
   https://t.me/YOUR_BOT_USERNAME
   ```

2. **ارسال دستور `/start`**
   - باید منوی اصلی نمایش داده شود
   
3. **دسترسی به پنل ادمین**
   - دکمه "🔐 پنل ادمین" را بزنید
   - باید به عنوان Super Admin شناخته شوید

---

## 🔧 دستورات مفید

### مدیریت سرویس

```bash
# شروع سرویس
sudo systemctl start codm-bot

# توقف سرویس
sudo systemctl stop codm-bot

# ری‌استارت سرویس
sudo systemctl restart codm-bot

# بررسی وضعیت
sudo systemctl status codm-bot

# غیرفعال کردن autostart
sudo systemctl disable codm-bot
```

### به‌روزرسانی ربات

```bash
cd /opt/codm-bot
git pull
sudo systemctl restart codm-bot
```

### پشتیبان‌گیری از دیتابیس

```bash
# ایجاد پشتیبان
sudo -u postgres pg_dump codm_bot > backup_$(date +%Y%m%d_%H%M%S).sql

# بازیابی از پشتیبان
sudo -u postgres psql codm_bot < backup_YYYYMMDD_HHMMSS.sql
```

---

## 🐛 عیب‌یابی

### ربات استارت نمی‌شود

```bash
# بررسی لاگ‌های خطا
sudo journalctl -u codm-bot -n 50 --no-pager

# بررسی فایل .env
cat .env

# تست دستی ربات
cd /opt/codm-bot
source venv/bin/activate
python main.py
```

### خطای اتصال به دیتابیس

```bash
# بررسی وضعیت PostgreSQL
sudo systemctl status postgresql

# تست اتصال به دیتابیس
sudo -u postgres psql -d codm_bot -c "SELECT version();"
```

### مشکل دسترسی ادمین

```bash
# افزودن دستی ادمین به دیتابیس (جایگزین USER_ID با آیدی خود)
sudo -u postgres psql -d codm_bot << EOF
INSERT INTO users (user_id) VALUES (YOUR_USER_ID) ON CONFLICT DO NOTHING;
INSERT INTO admins (user_id, is_active) VALUES (YOUR_USER_ID, TRUE) ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE;
INSERT INTO admin_roles (user_id, role_id) 
VALUES (YOUR_USER_ID, (SELECT id FROM roles WHERE name = 'super_admin')) 
ON CONFLICT DO NOTHING;
EOF
```

---

## 📞 پشتیبانی

- **مشکلات فنی**: [GitHub Issues](https://github.com/MasterALiReza/CoDM-Attach/issues)
- **مستندات بیشتر**: [README.md](README.md)
- **راه‌اندازی دیتابیس**: [DATABASE_SETUP.md](DATABASE_SETUP.md)

---

## 🔒 امنیت

⚠️ **نکات امنیتی:**
- فایل `.env` را هرگز به Git اضافه نکنید
- رمز عبور دیتابیس را قوی انتخاب کنید
- دسترسی SSH سرور را محدود کنید
- فایروال را فعال کنید
- پشتیبان‌گیری منظم انجام دهید

```bash
# فعال‌سازی فایروال
sudo ufw enable
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
```

---

✨ **موفق باشید!**
