#!/bin/bash

# ============================================================================
# CODM Bot Deployment Script for Ubuntu 24.04
# ============================================================================
# This script installs dependencies, sets up the environment, and configures 
# the bot as a systemd service.
#
# Usage: sudo ./deploy.sh
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Configuration
INSTALL_DIR="/opt/codm-bot"
BOT_USER="codm-bot"
SERVICE_NAME="codm-bot"

# ============================================================================
# Helper Functions
# ============================================================================

print_header() {
    echo -e "${CYAN}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║    🎮 CODM Attachments Bot - Deployment Script                 ║"
    echo "║                        Ubuntu 24.04                            ║"
    echo "║                                                                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

check_success() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ $1${NC}"
    else
        echo -e "${RED}❌ $1 failed${NC}"
        exit 1
    fi
}

generate_password() {
    # Generate a secure random password
    openssl rand -base64 24 | tr -dc 'a-zA-Z0-9!@#$%' | head -c 20
}

# ============================================================================
# Pre-flight Checks
# ============================================================================

print_header

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Please run as root: sudo ./deploy.sh${NC}"
    exit 1
fi

# Check if script is run from repo root
if [ ! -f "main.py" ] || [ ! -f "requirements.txt" ]; then
    echo -e "${RED}❌ Please run this script from the bot project root directory${NC}"
    echo -e "${YELLOW}   The directory should contain main.py and requirements.txt${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Pre-flight checks passed${NC}"

# ============================================================================
# Step 1: System Update & Dependencies
# ============================================================================

print_step "[1/7] 📦 Installing System Dependencies..."

apt update && apt upgrade -y
apt install -y python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib \
    git curl openssl acl \
    libpq-dev build-essential

check_success "System dependencies installed"

# ============================================================================
# Step 2: Create Bot User & Directory
# ============================================================================

print_step "[2/7] 👤 Setting Up Bot User & Directory..."

# Create dedicated user if not exists
if id "$BOT_USER" &>/dev/null; then
    echo "User $BOT_USER already exists."
else
    useradd -r -m -s /bin/bash $BOT_USER
    echo -e "${GREEN}✅ Created user: $BOT_USER${NC}"
fi

# Create install directory
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR exists. Updating..."
    # Backup existing .env if present
    if [ -f "$INSTALL_DIR/.env" ]; then
        cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.backup.$(date +%Y%m%d%H%M%S)"
        echo -e "${YELLOW}⚠️  Existing .env backed up${NC}"
    fi
else
    mkdir -p $INSTALL_DIR
    echo -e "${GREEN}✅ Created directory: $INSTALL_DIR${NC}"
fi

# Copy project files
echo "Copying project files..."
rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.env' --exclude='venv' --exclude='.agent_venv' \
    --exclude='logs/*' --exclude='backups/*' \
    . "$INSTALL_DIR/"

chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR"
chmod 750 "$INSTALL_DIR"

check_success "Project files installed"

# ============================================================================
# Step 3: Python Virtual Environment
# ============================================================================

print_step "[3/7] 🐍 Setting Up Python Environment..."

cd "$INSTALL_DIR"

# Create virtual environment
sudo -u $BOT_USER python3 -m venv venv
check_success "Virtual environment created"

# Upgrade pip and install dependencies
sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel setuptools
sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt
check_success "Python dependencies installed"

# ============================================================================
# Step 4: Database Configuration
# ============================================================================

print_step "[4/7] 🗄️ Configuring PostgreSQL Database..."

# Ensure PostgreSQL is running
systemctl start postgresql
systemctl enable postgresql

echo ""
echo -e "${CYAN}Database Setup Options:${NC}"
echo "  1. Create new local database (recommended for first install)"
echo "  2. Use existing database connection string"
echo ""
read -p "Select option (1 or 2): " DB_OPTION

if [ "$DB_OPTION" == "1" ]; then
    # Local database setup
    echo ""
    read -p "Database name [codm_bot_db]: " DB_NAME
    DB_NAME=${DB_NAME:-codm_bot_db}
    
    read -p "Database user [codm_bot_user]: " DB_USER
    DB_USER=${DB_USER:-codm_bot_user}
    
    # Generate secure random password
    DB_PASS=$(generate_password)
    echo -e "${YELLOW}Generated secure password for database user${NC}"
    
    echo ""
    echo -e "${CYAN}Creating database and user...${NC}"
    
    # Create user and database
    sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || true
    sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;" 2>/dev/null || true
    
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
    sudo -u postgres psql -c "ALTER USER $DB_USER WITH CREATEDB;"
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER ENCODING 'UTF8';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    
    check_success "Database user and database created"
    
    # Run schema setup
    echo -e "${CYAN}Setting up database schema...${NC}"
    
    # Connect to the new database and run setup script
    PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f "$INSTALL_DIR/scripts/setup_database.sql"
    
    check_success "Database schema created"
    
    DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME"
    
else
    # Existing database
    echo ""
    read -p "Enter PostgreSQL connection string: " DATABASE_URL
    
    # Extract user for ownership commands
    if [[ "$DATABASE_URL" =~ postgresql://([^:]+):([^@]+)@([^/]+)/(.+) ]]; then
        DB_USER="${BASH_REMATCH[1]}"
        DB_PASS="${BASH_REMATCH[2]}"
        DB_HOST="${BASH_REMATCH[3]}"
        DB_NAME="${BASH_REMATCH[4]}"
    fi
fi

echo -e "${GREEN}✅ Database configured${NC}"

# ============================================================================
# Step 5: Bot Configuration
# ============================================================================

print_step "[5/7] ⚙️ Configuring Bot..."

echo ""
read -p "Enter Telegram Bot Token (from @BotFather): " BOT_TOKEN

while [ -z "$BOT_TOKEN" ]; do
    echo -e "${RED}Bot token is required!${NC}"
    read -p "Enter Telegram Bot Token: " BOT_TOKEN
done

echo ""
read -p "Enter Super Admin Telegram ID (your numeric ID): " SUPER_ADMIN_ID

while ! [[ "$SUPER_ADMIN_ID" =~ ^[0-9]+$ ]]; do
    echo -e "${RED}Invalid ID. Must be a number!${NC}"
    read -p "Enter Super Admin Telegram ID: " SUPER_ADMIN_ID
done

# Create .env file
cat > "$INSTALL_DIR/.env" <<EOF
# ============================================================================
# CODM Bot Configuration
# Generated: $(date)
# ============================================================================

# Telegram Bot
BOT_TOKEN=$BOT_TOKEN
SUPER_ADMIN_ID=$SUPER_ADMIN_ID

# Database
DATABASE_URL=$DATABASE_URL
DATABASE_BACKEND=postgres

# Connection Pool
DB_POOL_SIZE=20
DB_POOL_MAX_OVERFLOW=10
DB_POOL_TIMEOUT=30

# Language
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
EOF

chown $BOT_USER:$BOT_USER "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"

check_success "Configuration file created"

# ============================================================================
# Step 6: Add Super Admin to Database
# ============================================================================

print_step "[6/7] 👑 Setting Up Super Admin..."

# Add super admin to database
PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" <<EOF
-- Insert super admin into users table
INSERT INTO users (user_id) VALUES ($SUPER_ADMIN_ID)
ON CONFLICT (user_id) DO NOTHING;

-- Insert into admins table
INSERT INTO admins (user_id, is_active) VALUES ($SUPER_ADMIN_ID, TRUE)
ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE;

-- Assign super_admin role
INSERT INTO admin_roles (user_id, role_id)
SELECT $SUPER_ADMIN_ID, id FROM roles WHERE name = 'super_admin'
ON CONFLICT DO NOTHING;
EOF

check_success "Super admin configured"

# ============================================================================
# Step 7: Systemd Service & CLI Tool
# ============================================================================

print_step "[7/7] 🚀 Setting Up Service & Management Tools..."

# Create systemd service
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

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$INSTALL_DIR/logs $INSTALL_DIR/backups
PrivateTmp=true

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload
systemctl enable $SERVICE_NAME

check_success "Systemd service created"

# Install wx-attach CLI tool
cp "$INSTALL_DIR/scripts/wx-attach" /usr/local/bin/wx-attach
chmod +x /usr/local/bin/wx-attach

check_success "Management CLI (wx-attach) installed"

# Create log and backup directories
mkdir -p "$INSTALL_DIR/logs" "$INSTALL_DIR/backups"
chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR/logs" "$INSTALL_DIR/backups"

# ============================================================================
# Completion
# ============================================================================

echo ""
echo -e "${GREEN}"
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║                                                                ║"
echo "║        🎉 Deployment Complete! 🎉                              ║"
echo "║                                                                ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${WHITE}Installation Summary:${NC}"
echo -e "  📁 Install Directory: ${CYAN}$INSTALL_DIR${NC}"
echo -e "  👤 Bot User: ${CYAN}$BOT_USER${NC}"
echo -e "  🗄️ Database: ${CYAN}$DB_NAME${NC}"
echo -e "  👑 Super Admin ID: ${CYAN}$SUPER_ADMIN_ID${NC}"
echo ""
echo -e "${WHITE}Quick Commands:${NC}"
echo -e "  ${GREEN}wx-attach${NC}              - Open management menu"
echo -e "  ${GREEN}wx-attach start${NC}        - Start the bot"
echo -e "  ${GREEN}wx-attach status${NC}       - Check bot status"
echo -e "  ${GREEN}wx-attach logs${NC}         - View bot logs"
echo ""
echo -e "${WHITE}Or use systemctl:${NC}"
echo -e "  ${YELLOW}systemctl start $SERVICE_NAME${NC}"
echo -e "  ${YELLOW}systemctl status $SERVICE_NAME${NC}"
echo -e "  ${YELLOW}journalctl -u $SERVICE_NAME -f${NC}"
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Ready to start? Run: ${BOLD}wx-attach start${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
