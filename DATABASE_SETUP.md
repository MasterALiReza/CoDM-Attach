# Database Setup - Quick Guide

## 🚀 Quick Setup (Recommended)

```bash
cd "f:\IDE Projects\Cursor Attach Bopt\codm-bot-modular"
python scripts/setup_database.py --drop-existing
```

این دستور:
- Database قدیمی را حذف می‌کند
- Database جدید می‌سازد: `codm_attachments_db`
- User جدید می‌سازد: `codm_bot_user`
- تمام tables و indexes را می‌سازد
- Data اولیه را وارد می‌کند
- فایل .env را به‌روز می‌کند

## 📋 Database Details

```
Database: codm_attachments_db
User: codm_bot_user
Password: CoDM_Secure_2025!@#
Host: localhost
Port: 5432
```

## 📊 What Gets Created

- ✅ 40+ tables
- ✅ 30+ indexes  
- ✅ 2 extensions (pg_trgm, unaccent)
- ✅ 8 weapon categories
- ✅ 4 default roles
- ✅ All constraints & foreign keys

## 🔧 Manual Setup (Alternative)

If the Python script doesn't work:

```bash
# 1. Connect as postgres
psql -U postgres

# 2. Create database
CREATE DATABASE codm_attachments_db OWNER codm_bot_user ENCODING 'UTF8';
\c codm_attachments_db

# 3. Run setup script
\i scripts/setup_database.sql

# 4. Exit
\q
```

## ✅ Verify Setup

```python
python -c "from core.database.database_pg import DatabasePostgres; db = DatabasePostgres(); print('✅ Connected!')"
```

## 📝 Update .env

The setup script automatically updates `.env`, but verify:

```env
DATABASE_URL=postgresql://codm_bot_user:CoDM_Secure_2025!@#@localhost:5432/codm_attachments_db
DB_NAME=codm_attachments_db
DB_USER=codm_bot_user
DB_PASSWORD=CoDM_Secure_2025!@#
```

## 🎯 Ready!

```bash
python main.py
```
