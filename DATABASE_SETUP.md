# Database Setup Guide

## 🚀 Quick Setup (Recommended)

The database is automatically set up when you run `deploy.sh`:

```bash
sudo ./deploy.sh
```

This will:
- Create PostgreSQL database and user with secure random password
- Set up all tables, indexes, and constraints
- Configure proper ownership and permissions
- Add the super admin to the database

## 📋 Manual Setup (Alternative)

If you need to set up the database manually:

### 1. Create Database User

```bash
# Connect as postgres superuser
sudo -u postgres psql

# Create user with password
CREATE USER codm_bot_user WITH PASSWORD 'your_secure_password';
ALTER USER codm_bot_user WITH CREATEDB;

# Exit
\q
```

### 2. Create Database

```bash
sudo -u postgres psql

CREATE DATABASE codm_bot_db OWNER codm_bot_user ENCODING 'UTF8';
GRANT ALL PRIVILEGES ON DATABASE codm_bot_db TO codm_bot_user;

\q
```

### 3. Run Schema Script

```bash
# Connect to the new database and run setup
PGPASSWORD='your_secure_password' psql -h localhost -U codm_bot_user -d codm_bot_db -f scripts/setup_database.sql
```

### 4. Configure Environment

Update your `.env` file:

```env
DATABASE_URL=postgresql://codm_bot_user:your_secure_password@localhost:5432/codm_bot_db
```

## 📊 Database Schema

The setup creates:

| Category | Count | Description |
|----------|-------|-------------|
| Tables | 40+ | Core data tables |
| Indexes | 30+ | Performance indexes |
| Extensions | 2 | pg_trgm, unaccent |
| Roles | 4 | super_admin, admin, moderator, support |
| Categories | 8 | Weapon categories |

### Key Tables

- `users` - Bot users
- `admins` - Admin accounts
- `weapons` - Weapon list
- `attachments` - Weapon attachments
- `user_attachments` - User submissions
- `tickets` - Support tickets
- `faqs` - FAQ entries

## ✅ Verify Setup

Run the health check:

```bash
python scripts/health_check.py
```

Or test connection manually:

```bash
cd /opt/codm-bot
venv/bin/python -c "from core.database.database_pg import DatabasePostgres; db = DatabasePostgres(); print('✅ Connected!')"
```

## 🔧 Management

Use the `wx-attach` CLI tool for database management:

```bash
wx-attach
# Then select option 8 (Database Utilities)
```

Available utilities:
- Test connection
- View statistics
- Backup database
- Reset database

## 🔒 Security Notes

1. **Never** commit `.env` file to version control
2. Use strong, unique passwords
3. Restrict database access to localhost only
4. Regular backups are stored in `/opt/codm-bot/backups/`
