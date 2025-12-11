#!/bin/bash

# ============================================================================
# CODM Bot - Advanced Deployment & Management Script
# ============================================================================
# این اسکریپت نصب، حذف، به‌روزرسانی و مدیریت کامل ربات را انجام می‌دهد
#
# Usage: sudo bash deploy.sh
# ============================================================================

set -e  # Exit on error

# ============================================================================
# Colors and Formatting
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
WHITE='\033[1;37m'
NC='\033[0m'
BOLD='\033[1m'

# ============================================================================
# Configuration
# ============================================================================

INSTALL_DIR="/opt/codm-bot"
BOT_USER="codm-bot"
SERVICE_NAME="codm-bot"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Default database credentials
DEFAULT_DB_NAME="codm_bot_db"
DEFAULT_DB_USER="codm_bot_user"

# ============================================================================
# Utility Functions
# ============================================================================

print_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════════╗"
    echo "║                                                                    ║"
    echo "║    ${WHITE}🎮 CODM Attachments Bot - Management System${CYAN}                    ║"
    echo "║                  ${YELLOW}نسخه پیشرفته و کامل${CYAN}                              ║"
    echo "║                                                                    ║"
    echo "╚════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC} ${BOLD}$1${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_step() {
    echo ""
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ️  $1${NC}"
}

# Generate secure random password
generate_password() {
    openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 24
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Confirm action
confirm() {
    local message="$1"
    local default="${2:-n}"
    
    if [ "$default" = "y" ]; then
        local prompt="[Y/n]"
    else
        local prompt="[y/N]"
    fi
    
    echo -e -n "${YELLOW}$message $prompt: ${NC}"
    read -r response
    
    response=${response:-$default}
    
    if [[ "$response" =~ ^[Yy]$ ]]; then
        return 0
    else
        return 1
    fi
}

# Press any key to continue
press_any_key() {
    echo ""
    echo -e "${CYAN}فشردن هر کلید برای ادامه...${NC}"
    read -n 1 -s
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "این اسکریپت باید با دسترسی root اجرا شود"
        echo -e "${YELLOW}لطفاً دستور را به صورت زیر اجرا کنید:${NC}"
        echo -e "${WHITE}sudo bash deploy.sh${NC}"
        exit 1
    fi
}

# ============================================================================
# Installation Functions
# ============================================================================

install_system_dependencies() {
    print_header "نصب وابستگی‌های سیستم"
    
    print_step "به‌روزرسانی لیست پکیج‌ها..."
    apt update -qq
    print_success "لیست پکیج‌ها به‌روز شد"
    
    print_step "نصب Python و ابزارهای توسعه..."
    apt install -y python3 python3-pip python3-venv python3-dev \
        build-essential libpq-dev git curl wget openssl acl >/dev/null 2>&1
    print_success "Python و ابزارهای توسعه نصب شد"
    
    print_step "نصب PostgreSQL..."
    apt install -y postgresql postgresql-contrib >/dev/null 2>&1
    systemctl start postgresql
    systemctl enable postgresql >/dev/null 2>&1
    print_success "PostgreSQL نصب و راه‌اندازی شد"
    
    print_step "نصب ابزارهای کمکی..."
    apt install -y rsync htop nano vim >/dev/null 2>&1
    print_success "ابزارهای کمکی نصب شد"
}

setup_database() {
    print_header "راه‌اندازی دیتابیس PostgreSQL"
    
    echo -e "${WHITE}انتخاب نوع راه‌اندازی دیتابیس:${NC}"
    echo ""
    echo "  ${GREEN}1.${NC} راه‌اندازی خودکار (پیشنهادی) ${CYAN}← اطلاعات به صورت خودکار تولید می‌شود${NC}"
    echo "  ${GREEN}2.${NC} راه‌اندازی سفارشی ${CYAN}← وارد کردن دستی اطلاعات${NC}"
    echo "  ${GREEN}3.${NC} استفاده از دیتابیس موجود ${CYAN}← اتصال به دیتابیس خارجی${NC}"
    echo ""
    
    echo -e -n "${YELLOW}انتخاب شما ${WHITE}[1/2/3]${YELLOW}: ${NC}"
    read db_setup_choice
    db_setup_choice=${db_setup_choice:-1}
    
    case $db_setup_choice in
        1)
            # Automatic setup
            print_step "راه‌اندازی خودکار دیتابیس..."
            
            DB_NAME="$DEFAULT_DB_NAME"
            DB_USER="$DEFAULT_DB_USER"
            DB_PASS=$(generate_password)
            DB_HOST="localhost"
            DB_PORT="5432"
            
            print_info "نام دیتابیس: ${WHITE}$DB_NAME${NC}"
            print_info "کاربر دیتابیس: ${WHITE}$DB_USER${NC}"
            print_info "رمز عبور: ${WHITE}$DB_PASS${NC}"
            ;;
            
        2)
            # Custom setup
            print_step "راه‌اندازی سفارشی دیتابیس..."
            
            echo -e -n "${CYAN}نام دیتابیس ${WHITE}[$DEFAULT_DB_NAME]${CYAN}: ${NC}"
            read DB_NAME
            DB_NAME=${DB_NAME:-$DEFAULT_DB_NAME}
            
            echo -e -n "${CYAN}نام کاربر ${WHITE}[$DEFAULT_DB_USER]${CYAN}: ${NC}"
            read DB_USER
            DB_USER=${DB_USER:-$DEFAULT_DB_USER}
            
            echo -e -n "${CYAN}رمز عبور ${YELLOW}(خالی = تولید خودکار)${CYAN}: ${NC}"
            read -s DB_PASS
            echo ""
            
            if [ -z "$DB_PASS" ]; then
                DB_PASS=$(generate_password)
                print_info "رمز عبور تولید شد: ${WHITE}$DB_PASS${NC}"
            fi
            
            DB_HOST="localhost"
            DB_PORT="5432"
            ;;
            
        3)
            # External database
            print_step "اتصال به دیتابیس خارجی..."
            
            echo -e -n "${CYAN}آدرس دیتابیس CONNECTION STRING: ${NC}"
            read DATABASE_URL
            
            if [[ "$DATABASE_URL" =~ postgresql://([^:]+):([^@]+)@([^:/]+):?([0-9]*)/(.+) ]]; then
                DB_USER="${BASH_REMATCH[1]}"
                DB_PASS="${BASH_REMATCH[2]}"
                DB_HOST="${BASH_REMATCH[3]}"
                DB_PORT="${BASH_REMATCH[4]:-5432}"
                DB_NAME="${BASH_REMATCH[5]}"
                
                print_success "اطلاعات دیتابیس استخراج شد"
                return 0
            else
                print_error "فرمت CONNECTION STRING نامعتبر است"
                exit 1
            fi
            ;;
            
        *)
            print_error "گزینه نامعتبر"
            exit 1
            ;;
    esac
    
    # Create database and user (for options 1 and 2)
    if [ "$db_setup_choice" != "3" ]; then
        print_step "ایجاد کاربر و دیتابیس..."
        
        # Drop existing if confirm
        if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
            print_warning "دیتابیس $DB_NAME از قبل وجود دارد"
            if confirm "آیا می‌خواهید دیتابیس موجود را حذف و مجدداً ایجاد کنید؟" "n"; then
                sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" >/dev/null 2>&1
                sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;" >/dev/null 2>&1
                print_success "دیتابیس قدیمی حذف شد"
            else
                print_info "از دیتابیس موجود استفاده می‌شود"
            fi
        fi
        
        # Create user
        if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
            sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" >/dev/null
            print_success "کاربر $DB_USER ایجاد شد"
        fi
        
        sudo -u postgres psql -c "ALTER USER $DB_USER WITH CREATEDB;" >/dev/null
        
        # Create database
        if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
            sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER ENCODING 'UTF8';" >/dev/null
            print_success "دیتابیس $DB_NAME ایجاد شد"
        fi
        
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" >/dev/null
        
        # Setup schema
        if [ -f "$INSTALL_DIR/scripts/setup_database.sql" ]; then
            print_step "راه‌اندازی جداول دیتابیس..."
            PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
                -f "$INSTALL_DIR/scripts/setup_database.sql" >/dev/null 2>&1
            print_success "جداول دیتابیس ایجاد شد"
        fi
    fi
    
    DATABASE_URL="postgresql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME"
    print_success "دیتابیس به طور کامل راه‌اندازی شد"
}

setup_bot_config() {
    print_header "تنظیمات ربات تلگرام"
    
    # Bot Token
    echo -e "${WHITE}توکن ربات تلگرام:${NC}"
    echo -e "${CYAN}💡 برای دریافت توکن به @BotFather مراجعه کنید${NC}"
    echo ""
    
    while true; do
        echo -e -n "${YELLOW}توکن ربات: ${NC}"
        read BOT_TOKEN
        
        if [ -z "$BOT_TOKEN" ]; then
            print_error "توکن نمی‌تواند خالی باشد"
        elif [[ ! "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
            print_error "فرمت توکن نامعتبر است"
        else
            break
        fi
    done
    
    print_success "توکن ربات ثبت شد"
    
    # Admin ID
    echo ""
    echo -e "${WHITE}شناسه ادمین اصلی (Super Admin):${NC}"
    echo -e "${CYAN}💡 برای دریافت ID خود به @userinfobot مراجعه کنید${NC}"
    echo ""
    
    while true; do
        echo -e -n "${YELLOW}Telegram User ID: ${NC}"
        read SUPER_ADMIN_ID
        
        if [ -z "$SUPER_ADMIN_ID" ]; then
            print_error "ID نمی‌تواند خالی باشد"
        elif [[ ! "$SUPER_ADMIN_ID" =~ ^[0-9]+$ ]]; then
            print_error "ID باید یک عدد باشد"
        else
            break
        fi
    done
    
    print_success "ادمین اصلی تنظیم شد"
}

create_env_file() {
    print_step "ایجاد فایل تنظیمات (.env)..."
    
    cat > "$INSTALL_DIR/.env" <<EOF
# ============================================================================
# CODM Bot Configuration
# تاریخ ایجاد: $(date '+%Y-%m-%d %H:%M:%S')
# ============================================================================

# Telegram Bot
BOT_TOKEN=$BOT_TOKEN
SUPER_ADMIN_ID=$SUPER_ADMIN_ID

# Database
DATABASE_URL=$DATABASE_URL
DATABASE_BACKEND=postgres

# PostgreSQL Connection Details
POSTGRES_HOST=$DB_HOST
POSTGRES_PORT=$DB_PORT
POSTGRES_DB=$DB_NAME
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=$DB_PASS

# Connection Pool Settings
DB_POOL_SIZE=20
DB_POOL_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30

# Language Settings
DEFAULT_LANG=fa
SUPPORTED_LANGS=fa,en
FALLBACK_LANG=en

# Environment
ENVIRONMENT=production
DEBUG_MODE=false

# Performance
CACHE_ENABLED=true
LOG_SLOW_QUERIES=true
SLOW_QUERY_THRESHOLD=100

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
EOF

    chown $BOT_USER:$BOT_USER "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    
    print_success "فایل تنظیمات ایجاد شد"
}

setup_super_admin() {
    print_step "اضافه کردن Super Admin به دیتابیس..."
    
    PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" <<EOF >/dev/null 2>&1
-- Insert user
INSERT INTO users (user_id) VALUES ($SUPER_ADMIN_ID)
ON CONFLICT (user_id) DO NOTHING;

-- Insert admin
INSERT INTO admins (user_id, is_active) VALUES ($SUPER_ADMIN_ID, TRUE)
ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE;

-- Assign super_admin role
INSERT INTO admin_roles (user_id, role_id)
SELECT $SUPER_ADMIN_ID, id FROM roles WHERE name = 'super_admin'
ON CONFLICT DO NOTHING;
EOF
    
    print_success "Super Admin به دیتابیس اضافه شد"
}

install_bot() {
    print_banner
    print_header "نصب ربات CODM Attachments"
    
    # Check if already installed
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_warning "ربات در حال حاضر نصب و در حال اجرا است"
        if ! confirm "آیا می‌خواهید نصب مجدد انجام شود؟" "n"; then
            return
        fi
        systemctl stop $SERVICE_NAME
    fi
    
    # Step 1: Install system dependencies
    if confirm "آیا می‌خواهید وابستگی‌های سیستم نصب شوند؟ (PostgreSQL, Python, ...)" "y"; then
        install_system_dependencies
    else
        print_warning "نصب وابستگی‌ها رد شد"
    fi
    
    # Step 2: Create user and directory
    print_header "ایجاد کاربر و دایرکتوری"
    
    if ! id "$BOT_USER" &>/dev/null; then
        useradd -r -m -s /bin/bash $BOT_USER
        print_success "کاربر $BOT_USER ایجاد شد"
    else
        print_info "کاربر $BOT_USER از قبل وجود دارد"
    fi
    
    mkdir -p "$INSTALL_DIR"
    
    # Copy files
    print_step "کپی کردن فایل‌های پروژه..."
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.env' --exclude='venv' --exclude='.agent_venv' \
        --exclude='logs/*' --exclude='backups/*' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/" >/dev/null
    
    chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR"
    chmod 750 "$INSTALL_DIR"
    print_success "فایل‌های پروژه کپی شد"
    
    # Step 3: Python environment
    print_header "راه‌اندازی محیط Python"
    
    cd "$INSTALL_DIR"
    
    print_step "ایجاد محیط مجازی Python..."
    sudo -u $BOT_USER python3 -m venv venv
    print_success "محیط مجازی ایجاد شد"
    
    print_step "نصب کتابخانه‌های Python..."
    sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel setuptools >/dev/null 2>&1
    sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt >/dev/null 2>&1
    print_success "کتابخانه‌های Python نصب شد"
    
    # Step 4: Database setup
    setup_database
    
    # Step 5: Bot configuration
    setup_bot_config
    
    # Step 6: Create .env file
    create_env_file
    
    # Step 7: Setup super admin
    setup_super_admin
    
    # Step 8: Create systemd service
    print_header "راه‌اندازی سرویس Systemd"
    
    cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=CODM Attachments Telegram Bot
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
EnvironmentFile=$INSTALL_DIR/.env

# Security
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/logs $INSTALL_DIR/backups
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF
    
    systemctl daemon-reload
    systemctl enable $SERVICE_NAME >/dev/null 2>&1
    print_success "سرویس systemd ایجاد شد"
    
    # Install wx-attach CLI tool
    print_step "نصب ابزار مدیریت (wx-attach)..."
    cp "$SCRIPT_DIR/scripts/wx-attach" /usr/local/bin/wx-attach
    chmod +x /usr/local/bin/wx-attach
    print_success "ابزار مدیریت نصب شد"
    
    # Step 9: Create directories
    mkdir -p "$INSTALL_DIR/logs" "$INSTALL_DIR/backups"
    chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR/logs" "$INSTALL_DIR/backups"
    
    # Installation complete
    echo ""
    print_success "🎉 نصب با موفقیت انجام شد!"
    echo ""
    
    if confirm "آیا می‌خواهید ربات الان شروع شود؟" "y"; then
        systemctl start $SERVICE_NAME
        sleep 2
        if systemctl is-active --quiet $SERVICE_NAME; then
            print_success "ربات با موفقیت شروع شد"
            echo ""
            echo -e "${CYAN}برای مشاهده لاگ‌ها: ${WHITE}journalctl -u $SERVICE_NAME -f${NC}"
        else
            print_error "خطا در شروع ربات"
            echo -e "${YELLOW}برای مشاهده خطا: ${WHITE}systemctl status $SERVICE_NAME${NC}"
        fi
    fi
    
    press_any_key
}

# ============================================================================
# Uninstall Function
# ============================================================================

uninstall_bot() {
    print_banner
    print_header "حذف ربات CODM Attachments"
    
    print_warning "این عملیات تمام فایل‌ها و تنظیمات ربات را حذف می‌کند"
    print_warning "دیتابیس و کاربر PostgreSQL نیز حذف خواهند شد"
    echo ""
    
    if ! confirm "آیا مطمئن هستید که می‌خواهید ربات را حذف کنید?" "n"; then
        print_info "عملیات لغو شد"
        press_any_key
        return
    fi
    
    echo ""
    if ! confirm "آیا واقعاً مطمئن هستید؟ این عملیات قابل بازگشت نیست!" "n"; then
        print_info "عملیات لغو شد"
        press_any_key
        return
    fi
    
    print_step "توقف سرویس..."
    if systemctl is-active --quiet $SERVICE_NAME; then
        systemctl stop $SERVICE_NAME
        print_success "سرویس متوقف شد"
    fi
    
    systemctl disable $SERVICE_NAME >/dev/null 2>&1 || true
    
    print_step "حذف سرویس systemd..."
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    print_success "سرویس حذف شد"
    
    # Backup before delete
    if [ -d "$INSTALL_DIR" ]; then
        print_step "ایجاد بکاپ قبل از حذف..."
        backup_dir="/tmp/codm-bot-backup-$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        
        if [ -f "$INSTALL_DIR/.env" ]; then
            cp "$INSTALL_DIR/.env" "$backup_dir/"
        fi
        
        if [ -d "$INSTALL_DIR/logs" ]; then
            cp -r "$INSTALL_DIR/logs" "$backup_dir/" 2>/dev/null || true
        fi
        
        print_success "بکاپ ایجاد شد: $backup_dir"
    fi
    
    print_step "حذف فایل‌های نصب..."
    rm -rf "$INSTALL_DIR"
    print_success "فایل‌ها حذف شد"
    
    print_step "حذف کاربر سیستم..."
    if id "$BOT_USER" &>/dev/null; then
        userdel -r $BOT_USER 2>/dev/null || true
        print_success "کاربر حذف شد"
    fi
    
    # Database removal
    if confirm "آیا می‌خواهید دیتابیس و کاربر PostgreSQL هم حذف شوند?" "n"; then
        print_step "حذف دیتابیس..."
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DEFAULT_DB_NAME;" 2>/dev/null || true
        sudo -u postgres psql -c "DROP USER IF EXISTS $DEFAULT_DB_USER;" 2>/dev/null || true
        print_success "دیتابیس حذف شد"
    fi
    
    echo ""
    print_success "ربات به طور کامل حذف شد"
    
    if [ -d "$backup_dir" ]; then
        echo ""
        print_info "فایل‌های بکاپ در: $backup_dir"
    fi
    
    press_any_key
}

# ============================================================================
# Update Function
# ============================================================================

update_bot() {
    print_banner
    print_header "به‌روزرسانی ربات"
    
    if [ ! -d "$INSTALL_DIR" ]; then
        print_error "ربات نصب نشده است"
        press_any_key
        return
    fi
    
    print_step "بررسی وضعیت Git..."
    
    cd "$SCRIPT_DIR"
    
    if [ ! -d ".git" ]; then
        print_warning "این یک مخزن Git نیست"
        print_info "فایل‌ها به صورت دستی کپی می‌شوند"
    else
        print_step "دریافت آخرین تغییرات از GitHub..."
        git fetch origin
        
        LOCAL=$(git rev-parse @)
        REMOTE=$(git rev-parse @{u})
        
        if [ $LOCAL = $REMOTE ]; then
            print_info "شما از آخرین نسخه استفاده می‌کنید"
            if ! confirm "آیا می‌خواهید به هر حال فایل‌ها کپی شوند؟" "n"; then
                press_any_key
                return
            fi
        else
            print_info "نسخه جدید موجود است"
            git pull
            print_success "کد به‌روز شد"
        fi
    fi
    
    # Backup .env
    if [ -f "$INSTALL_DIR/.env" ]; then
        cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"
        print_success "فایل .env بکاپ شد"
    fi
    
    # Stop service
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_step "توقف موقت سرویس..."
        systemctl stop $SERVICE_NAME
    fi
    
    # Copy new files
    print_step "کپی کردن فایل‌های جدید..."
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.env' --exclude='venv' --exclude='.agent_venv' \
        --exclude='logs/*' --exclude='backups/*' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/" >/dev/null
    
    chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR"
    print_success "فایل‌ها به‌روز شد"
    
    # Update Python dependencies
    print_step "به‌روزرسانی کتابخانه‌های Python..."
    sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip >/dev/null 2>&1
    sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --upgrade >/dev/null 2>&1
    print_success "کتابخانه‌ها به‌روز شد"
    
    # Restart service
    print_step "راه‌اندازی مجدد سرویس..."
    systemctl start $SERVICE_NAME
    sleep 2
    
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_success "ربات با موفقیت به‌روز و راه‌اندازی شد"
    else
        print_error "خطا در راه‌اندازی ربات"
        echo -e "${YELLOW}برای بررسی: ${WHITE}systemctl status $SERVICE_NAME${NC}"
    fi
    
    press_any_key
}

# ============================================================================
# Backup & Restore Functions
# ============================================================================

backup_bot() {
    print_banner
    print_header "بکاپ از ربات و دیتابیس"
    
    backup_dir="/opt/codm-bot-backups"
    mkdir -p "$backup_dir"
    
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_name="codm-bot-backup-$timestamp"
    backup_path="$backup_dir/$backup_name"
    
    print_step "ایجاد پوشه بکاپ..."
    mkdir -p "$backup_path"
    
    # Backup .env
    if [ -f "$INSTALL_DIR/.env" ]; then
        print_step "بکاپ فایل تنظیمات..."
        cp "$INSTALL_DIR/.env" "$backup_path/"
        print_success "فایل .env بکاپ شد"
    fi
    
    # Backup database
    if [ -f "$INSTALL_DIR/.env" ]; then
        source "$INSTALL_DIR/.env"
        
        print_step "بکاپ دیتابیس..."
        
        if [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_DB" ]; then
            PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "${POSTGRES_HOST:-localhost}" \
                -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
                > "$backup_path/database.sql" 2>/dev/null
            
            if [ $? -eq 0 ]; then
                print_success "دیتابیس بکاپ شد"
            else
                print_warning "خطا در بکاپ دیتابیس"
            fi
        fi
    fi
    
    # Create archive
    print_step "فشرده‌سازی بکاپ..."
    cd "$backup_dir"
    tar -czf "${backup_name}.tar.gz" "$backup_name" 2>/dev/null
    rm -rf "$backup_name"
    
    print_success "بکاپ با موفقیت ایجاد شد"
    echo ""
    print_info "مسیر بکاپ: ${WHITE}$backup_dir/${backup_name}.tar.gz${NC}"
    
    press_any_key
}

# ============================================================================
# Status & Logs Functions
# ============================================================================

show_status() {
    print_banner
    print_header "وضعیت ربات"
    
    echo -e "${WHITE}سرویس Systemd:${NC}"
    systemctl status $SERVICE_NAME --no-pager -l
    
    echo ""
    echo -e "${WHITE}دیسک:${NC}"
    df -h "$INSTALL_DIR" 2>/dev/null || df -h /
    
    echo ""
    echo -e "${WHITE}حافظه:${NC}"
    free -h
    
    press_any_key
}

show_logs() {
    print_banner
    print_header "لاگ‌های ربات"
    
    echo -e "${CYAN}در حال نمایش 50 خط آخر لاگ...${NC}"
    echo -e "${YELLOW}برای خروج Ctrl+C را فشار دهید${NC}"
    echo ""
    
    journalctl -u $SERVICE_NAME -n 50 --no-pager
    
    echo ""
    if confirm "آیا می‌خواهید لاگ‌های زنده را مشاهده کنید؟" "y"; then
        journalctl -u $SERVICE_NAME -f
    fi
}

# ============================================================================
# Main Menu
# ============================================================================

show_main_menu() {
    while true; do
        print_banner
        
        # Show status indicator
        if systemctl is-active --quiet $SERVICE_NAME; then
            status_icon="${GREEN}●${NC}"
            status_text="${GREEN}در حال اجرا${NC}"
        else
            status_icon="${RED}●${NC}"
            status_text="${RED}غیرفعال${NC}"
        fi
        
        echo -e "  وضعیت ربات: $status_icon $status_text"
        echo ""
        echo -e "${CYAN}╔════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}║${NC}                      ${BOLD}منوی اصلی${NC}                                    ${CYAN}║${NC}"
        echo -e "${CYAN}╠════════════════════════════════════════════════════════════════════╣${NC}"
        echo -e "${CYAN}║${NC}                                                                    ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}1.${NC} نصب ربات ${YELLOW}(نصب کامل از صفر)${NC}                              ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}2.${NC} حذف ربات ${RED}(حذف کامل ربات و تنظیمات)${NC}                      ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}3.${NC} به‌روزرسانی ربات ${CYAN}(دریافت آخرین نسخه)${NC}                     ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}4.${NC} شروع ربات                                                   ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}5.${NC} توقف ربات                                                    ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}6.${NC} ری‌استارت ربات                                               ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}7.${NC} وضعیت ربات ${BLUE}(مشاهده وضعیت سرویس)${NC}                        ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}8.${NC} مشاهده لاگ‌ها                                                ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}9.${NC} بکاپ ${MAGENTA}(بکاپ از دیتابیس و تنظیمات)${NC}                    ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}0.${NC} خروج                                                         ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}                                                                    ${CYAN}║${NC}"
        echo -e "${CYAN}╚════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        
        echo -e -n "${YELLOW}انتخاب شما ${WHITE}[0-9]${YELLOW}: ${NC}"
        read choice
        
        case $choice in
            1) install_bot ;;
            2) uninstall_bot ;;
            3) update_bot ;;
            4)
                print_step "شروع ربات..."
                systemctl start $SERVICE_NAME
                sleep 1
                if systemctl is-active --quiet $SERVICE_NAME; then
                    print_success "ربات شروع شد"
                else
                    print_error "خطا در شروع ربات"
                fi
                press_any_key
                ;;
            5)
                print_step "توقف ربات..."
                systemctl stop $SERVICE_NAME
                sleep 1
                print_success "ربات متوقف شد"
                press_any_key
                ;;
            6)
                print_step "ری‌استارت ربات..."
                systemctl restart $SERVICE_NAME
                sleep 2
                if systemctl is-active --quiet $SERVICE_NAME; then
                    print_success "ربات ری‌استارت شد"
                else
                    print_error "خطا در ری‌استارت"
                fi
                press_any_key
                ;;
            7) show_status ;;
            8) show_logs ;;
            9) backup_bot ;;
            0)
                clear
                echo -e "${GREEN}خداحافظ! 👋${NC}"
                exit 0
                ;;
            *)
                print_error "گزینه نامعتبر"
                sleep 1
                ;;
        esac
    done
}

# ============================================================================
# Entry Point
# ============================================================================

check_root
show_main_menu
