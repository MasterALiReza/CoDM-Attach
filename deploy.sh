#!/bin/bash

# ============================================================================
# CODM Bot - Advanced Deployment & Management Script
# ============================================================================
# This script handles installation, uninstallation, updates, and management of the bot
#
# Usage: sudo bash deploy.sh
# ============================================================================

set -e  # Exit on error

# ============================================================================
# Colors and Formatting
# ============================================================================

if command -v tput >/dev/null 2>&1; then
    RED=$(tput setaf 1)
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    BLUE=$(tput setaf 4)
    MAGENTA=$(tput setaf 5)
    CYAN=$(tput setaf 6)
    WHITE=$(tput setaf 7)
    NC=$(tput sgr0)
    BOLD=$(tput bold)
else
    RED='\e[0;31m'
    GREEN='\e[0;32m'
    YELLOW='\e[1;33m'
    BLUE='\e[0;34m'
    MAGENTA='\e[0;35m'
    CYAN='\e[0;36m'
    WHITE='\e[1;37m'
    NC='\e[0m'
    BOLD='\e[1m'
fi

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
    echo "║                  ${YELLOW}Advanced Edition${CYAN}                                 ║"
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
    echo -e "${CYAN}Press any key to continue...${NC}"
    read -n 1 -s
}

# Check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        print_error "This script must be run as root"
        echo -e "${YELLOW}Please run the command as follows:${NC}"
        echo -e "${WHITE}sudo bash deploy.sh${NC}"
        exit 1
    fi
}

# ============================================================================
# Installation Functions
# ============================================================================

install_system_dependencies() {
    print_header "Installing System Dependencies"
    
    print_step "Updating package list..."
    apt update -qq
    print_success "Package list updated"
    
    print_step "Installing Python and development tools..."
    apt install -y python3 python3-pip python3-venv python3-dev \
        build-essential libpq-dev git curl wget openssl acl >/dev/null 2>&1
    print_success "Python and development tools installed"
    
    print_step "Installing PostgreSQL..."
    apt install -y postgresql postgresql-contrib >/dev/null 2>&1
    systemctl start postgresql
    systemctl enable postgresql >/dev/null 2>&1
    print_success "PostgreSQL installed and started"
    
    print_step "Installing utility tools..."
    apt install -y rsync htop nano vim >/dev/null 2>&1
    print_success "Utility tools installed"
}

setup_database() {
    print_header "Setting up PostgreSQL Database"
    
    echo -e "${WHITE}Select Database Setup Type:${NC}"
    echo ""
    echo "  ${GREEN}1.${NC} Automatic Setup (Recommended) ${CYAN}← Auto-generates credentials${NC}"
    echo "  ${GREEN}2.${NC} Custom Setup ${CYAN}← Manual credential entry${NC}"
    echo "  ${GREEN}3.${NC} Use Existing Database ${CYAN}← Connect to external DB${NC}"
    echo ""
    
    echo -e -n "${YELLOW}Your choice ${WHITE}[1/2/3]${YELLOW}: ${NC}"
    read db_setup_choice
    db_setup_choice=${db_setup_choice:-1}
    
    case $db_setup_choice in
        1)
            # Automatic setup
            print_step "Automatic database setup..."
            
            DB_NAME="$DEFAULT_DB_NAME"
            DB_USER="$DEFAULT_DB_USER"
            DB_PASS=$(generate_password)
            DB_HOST="localhost"
            DB_PORT="5432"
            
            print_info "Database Name: ${WHITE}$DB_NAME${NC}"
            print_info "Database User: ${WHITE}$DB_USER${NC}"
            print_info "Password: ${WHITE}$DB_PASS${NC}"
            ;;
            
        2)
            # Custom setup
            print_step "Custom database setup..."
            
            echo -e -n "${CYAN}Database Name ${WHITE}[$DEFAULT_DB_NAME]${CYAN}: ${NC}"
            read DB_NAME
            DB_NAME=${DB_NAME:-$DEFAULT_DB_NAME}
            
            echo -e -n "${CYAN}Database User ${WHITE}[$DEFAULT_DB_USER]${CYAN}: ${NC}"
            read DB_USER
            DB_USER=${DB_USER:-$DEFAULT_DB_USER}
            
            echo -e -n "${CYAN}Password ${YELLOW}(Empty = Auto-generate)${CYAN}: ${NC}"
            read -s DB_PASS
            echo ""
            
            if [ -z "$DB_PASS" ]; then
                DB_PASS=$(generate_password)
                print_info "Generated Password: ${WHITE}$DB_PASS${NC}"
            fi
            
            DB_HOST="localhost"
            DB_PORT="5432"
            ;;
            
        3)
            # External database
            print_step "Connecting to external database..."
            
            echo -e -n "${CYAN}Database CONNECTION STRING: ${NC}"
            read DATABASE_URL
            
            if [[ "$DATABASE_URL" =~ postgresql://([^:]+):([^@]+)@([^:/]+):?([0-9]*)/(.+) ]]; then
                DB_USER="${BASH_REMATCH[1]}"
                DB_PASS="${BASH_REMATCH[2]}"
                DB_HOST="${BASH_REMATCH[3]}"
                DB_PORT="${BASH_REMATCH[4]:-5432}"
                DB_NAME="${BASH_REMATCH[5]}"
                
                print_success "Database credentials extracted"
                return 0
            else
                print_error "Invalid CONNECTION STRING format"
                exit 1
            fi
            ;;
            
        *)
            print_error "Invalid option"
            exit 1
            ;;
    esac
    
    # Create database and user (for options 1 and 2)
    if [ "$db_setup_choice" != "3" ]; then
        print_step "Creating user and database..."
        
        # Drop existing if confirm
        if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
            print_warning "Database $DB_NAME already exists"
            if confirm "Do you want to drop and recreate the existing database?" "n"; then
                sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" >/dev/null 2>&1
                sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;" >/dev/null 2>&1
                print_success "Old database removed"
            else
                print_info "Using existing database"
            fi
        fi
        
        # Create user
        if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
            sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" >/dev/null
            print_success "User $DB_USER created"
        fi
        
        sudo -u postgres psql -c "ALTER USER $DB_USER WITH CREATEDB;" >/dev/null
        
        # Create database
        if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
            sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER ENCODING 'UTF8';" >/dev/null
            print_success "Database $DB_NAME created"
        fi
        
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" >/dev/null
        
        # Setup schema
        if [ -f "$INSTALL_DIR/scripts/setup_database.sql" ]; then
            print_step "Setting up database schema..."
            PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" \
                -f "$INSTALL_DIR/scripts/setup_database.sql" >/dev/null 2>&1
            print_success "Database schema created"
        fi
    fi
    
    DATABASE_URL="postgresql://$DB_USER:$DB_PASS@$DB_HOST:$DB_PORT/$DB_NAME"
    print_success "Database setup complete"
}



setup_bot_config() {
    print_header "Telegram Bot Configuration"
    
    # Bot Token
    echo -e "${WHITE}Telegram Bot Token:${NC}"
    echo -e "${CYAN}💡 Get your token from @BotFather${NC}"
    echo ""
    
    while true; do
        echo -e -n "${YELLOW}Bot Token: ${NC}"
        read BOT_TOKEN
        
        if [ -z "$BOT_TOKEN" ]; then
            print_error "Token cannot be empty"
        elif [[ ! "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
            print_error "Invalid token format"
        else
            break
        fi
    done
    
    print_success "Bot token saved"
    
    # Admin ID
    echo ""
    echo -e "${WHITE}Super Admin Telegram ID:${NC}"
    echo -e "${CYAN}💡 Get your ID from @userinfobot${NC}"
    echo ""
    
    while true; do
        echo -e -n "${YELLOW}Telegram User ID: ${NC}"
        read SUPER_ADMIN_ID
        
        if [ -z "$SUPER_ADMIN_ID" ]; then
            print_error "ID cannot be empty"
        elif [[ ! "$SUPER_ADMIN_ID" =~ ^[0-9]+$ ]]; then
            print_error "ID must be a number"
        else
            break
        fi
    done
    
    print_success "Super Admin set"
}

create_env_file() {
    print_step "Creating configuration file (.env)..."
    
    cat > "$INSTALL_DIR/.env" <<EOF
# ============================================================================
# CODM Bot Configuration
# Created: $(date '+%Y-%m-%d %H:%M:%S')
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
    
    print_success "Configuration file created"
}

setup_super_admin() {
    print_step "Adding Super Admin to database..."
    
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
    
    print_success "Super Admin added to database"
}

install_bot() {
    print_banner
    print_header "Installing CODM Attachments Bot"
    
    # Check if already installed
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_warning "Bot is already installed and running"
        if ! confirm "Do you want to reinstall?" "n"; then
            return
        fi
        systemctl stop $SERVICE_NAME
    fi
    
    # Step 1: Install system dependencies
    if confirm "Do you want to install system dependencies? (PostgreSQL, Python, ...)" "y"; then
        install_system_dependencies
    else
        print_warning "Skipping dependency installation"
    fi
    
    # Step 2: Create user and directory
    print_header "Creating User and Directory"
    
    if ! id "$BOT_USER" &>/dev/null; then
        useradd -r -m -s /bin/bash $BOT_USER
        print_success "User $BOT_USER created"
    else
        print_info "User $BOT_USER already exists"
    fi
    
    mkdir -p "$INSTALL_DIR"
    
    # Copy files
    print_step "Copying project files..."
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.env' --exclude='venv' --exclude='.agent_venv' \
        --exclude='logs/*' --exclude='backups/*' \
        --exclude='.vscode' --exclude='.idea' \
        --exclude='deploy.bat' --exclude='setup_windows.ps1' --exclude='*.spec' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/" >/dev/null
    
    chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR"
    chmod 750 "$INSTALL_DIR"
    print_success "Project files copied"
    
    # Step 3: Python environment
    print_header "Setting up Python Environment"
    
    cd "$INSTALL_DIR"
    
    print_step "Creating Python virtual environment..."
    sudo -u $BOT_USER python3 -m venv venv
    print_success "Virtual environment created"
    
    print_step "Installing Python libraries..."
    sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip wheel setuptools >/dev/null 2>&1
    sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt >/dev/null 2>&1
    print_success "Python libraries installed"
    
    # Step 4: Database setup
    setup_database
    
    # Step 5: Bot configuration
    setup_bot_config
    
    # Step 6: Create .env file
    create_env_file
    
    # Step 7: Setup super admin
    setup_super_admin
    

    
    # Step 9: Create systemd service
    print_header "Setting up Systemd Service"
    
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
    print_success "Systemd service created"
    
    # Install wx-attach CLI tool
    print_step "Installing management tool (wx-attach)..."
    cp "$SCRIPT_DIR/scripts/wx-attach" /usr/local/bin/wx-attach
    chmod +x /usr/local/bin/wx-attach
    print_success "Management tool installed"
    
    # Step 9: Create directories
    mkdir -p "$INSTALL_DIR/logs" "$INSTALL_DIR/backups"
    chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR/logs" "$INSTALL_DIR/backups"
    
    # Installation complete
    echo ""
    print_success "🎉 Installation Complete!"
    echo ""
    
    if confirm "Do you want to start the bot now?" "y"; then
        systemctl start $SERVICE_NAME
        sleep 2
        if systemctl is-active --quiet $SERVICE_NAME; then
            print_success "Bot started successfully"
            echo ""
            echo -e "${CYAN}To view logs: ${WHITE}journalctl -u $SERVICE_NAME -f${NC}"
        else
            print_error "Error starting bot"
            echo -e "${YELLOW}Check status: ${WHITE}systemctl status $SERVICE_NAME${NC}"
        fi
    fi
    
    press_any_key
}

# ============================================================================
# Uninstall Function
# ============================================================================

uninstall_bot() {
    print_banner
    print_header "Uninstall CODM Attachments Bot"
    
    print_warning "This operation will remove all bot files and configurations"
    print_warning "PostgreSQL database and user will also be removed"
    echo ""
    
    if ! confirm "Are you sure you want to uninstall the bot?" "n"; then
        print_info "Operation cancelled"
        press_any_key
        return
    fi
    
    echo ""
    if ! confirm "Are you really sure? This cannot be undone!" "n"; then
        print_info "Operation cancelled"
        press_any_key
        return
    fi
    
    print_step "Stopping service..."
    if systemctl is-active --quiet $SERVICE_NAME; then
        systemctl stop $SERVICE_NAME
        print_success "Service stopped"
    fi
    
    systemctl disable $SERVICE_NAME >/dev/null 2>&1 || true
    
    print_step "Removing systemd service..."
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload
    print_success "Service removed"
    
    # Backup before delete
    if [ -d "$INSTALL_DIR" ]; then
        print_step "Creating backup before removal..."
        backup_dir="/tmp/codm-bot-backup-$(date +%Y%m%d_%H%M%S)"
        mkdir -p "$backup_dir"
        
        if [ -f "$INSTALL_DIR/.env" ]; then
            cp "$INSTALL_DIR/.env" "$backup_dir/"
        fi
        
        if [ -d "$INSTALL_DIR/logs" ]; then
            cp -r "$INSTALL_DIR/logs" "$backup_dir/" 2>/dev/null || true
        fi
        
        print_success "Backup created: $backup_dir"
    fi
    
    print_step "Removing installation files..."
    rm -rf "$INSTALL_DIR"
    print_success "Files removed"
    
    print_step "Removing system user..."
    if id "$BOT_USER" &>/dev/null; then
        userdel -r $BOT_USER 2>/dev/null || true
        print_success "User removed"
    fi
    
    # Database removal
    if confirm "Do you want to remove PostgreSQL database and user?" "n"; then
        print_step "Removing database..."
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DEFAULT_DB_NAME;" 2>/dev/null || true
        sudo -u postgres psql -c "DROP USER IF EXISTS $DEFAULT_DB_USER;" 2>/dev/null || true
        print_success "Database removed"
    fi
    
    echo ""
    print_success "Bot completely uninstalled"
    
    if [ -d "$backup_dir" ]; then
        echo ""
        print_info "Backup files located at: $backup_dir"
    fi
    
    press_any_key
}

# ============================================================================
# Update Function
# ============================================================================

update_bot() {
    print_banner
    print_header "Update Bot"
    
    if [ ! -d "$INSTALL_DIR" ]; then
        print_error "Bot is not installed"
        press_any_key
        return
    fi
    
    print_step "Checking Git status..."
    
    cd "$SCRIPT_DIR"
    
    if [ ! -d ".git" ]; then
        print_warning "Not a Git repository"
        print_info "Files will be copied manually"
    else
        print_step "Fetching latest changes from GitHub..."
        git fetch origin
        
        LOCAL=$(git rev-parse @)
        REMOTE=$(git rev-parse @{u})
        
        if [ $LOCAL = $REMOTE ]; then
            print_info "You are using the latest version"
            if ! confirm "Do you want to copy files anyway?" "n"; then
                press_any_key
                return
            fi
        else
            print_info "New version available"
            git pull
            print_success "Code updated"
        fi
    fi
    
    # Backup .env
    if [ -f "$INSTALL_DIR/.env" ]; then
        cp "$INSTALL_DIR/.env" "$INSTALL_DIR/.env.backup.$(date +%Y%m%d_%H%M%S)"
        print_success ".env file backed up"
    fi
    
    # Stop service
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_step "Stopping service temporarily..."
        systemctl stop $SERVICE_NAME
    fi
    
    # Copy new files
    print_step "Copying new files..."
    rsync -av --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
        --exclude='.env' --exclude='venv' --exclude='.agent_venv' \
        --exclude='logs/*' --exclude='backups/*' \
        --exclude='.vscode' --exclude='.idea' \
        --exclude='deploy.bat' --exclude='setup_windows.ps1' --exclude='*.spec' \
        "$SCRIPT_DIR/" "$INSTALL_DIR/" >/dev/null
    
    chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR"
    print_success "Files updated"
    
    # Update Python dependencies
    print_step "Updating Python libraries..."
    sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip >/dev/null 2>&1
    sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" --upgrade >/dev/null 2>&1
    print_success "Libraries updated"
    

    
    # Restart service
    print_step "Restarting service..."
    systemctl start $SERVICE_NAME
    sleep 2
    
    if systemctl is-active --quiet $SERVICE_NAME; then
        print_success "Bot updated and restarted successfully"
    else
        print_error "Error starting bot"
        echo -e "${YELLOW}Check status: ${WHITE}systemctl status $SERVICE_NAME${NC}"
    fi
    
    press_any_key
}

# ============================================================================
# Backup & Restore Functions
# ============================================================================

backup_bot() {
    print_banner
    print_header "Backup Bot and Database"
    
    backup_dir="/opt/codm-bot-backups"
    mkdir -p "$backup_dir"
    
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_name="codm-bot-backup-$timestamp"
    backup_path="$backup_dir/$backup_name"
    
    print_step "Creating backup directory..."
    mkdir -p "$backup_path"
    
    # Backup .env
    if [ -f "$INSTALL_DIR/.env" ]; then
        print_step "Backing up configuration file..."
        cp "$INSTALL_DIR/.env" "$backup_path/"
        print_success ".env file backed up"
    fi
    
    # Backup database
    if [ -f "$INSTALL_DIR/.env" ]; then
        source "$INSTALL_DIR/.env"
        
        print_step "Backing up database..."
        
        if [ -n "$POSTGRES_USER" ] && [ -n "$POSTGRES_DB" ]; then
            PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h "${POSTGRES_HOST:-localhost}" \
                -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
                > "$backup_path/database.sql" 2>/dev/null
            
            if [ $? -eq 0 ]; then
                print_success "Database backed up"
            else
                print_warning "Error backing up database"
            fi
        fi
    fi
    
    # Create archive
    print_step "Compressing backup..."
    cd "$backup_dir"
    tar -czf "${backup_name}.tar.gz" "$backup_name" 2>/dev/null
    rm -rf "$backup_name"
    
    print_success "Backup created successfully"
    echo ""
    print_info "Backup path: ${WHITE}$backup_dir/${backup_name}.tar.gz${NC}"
    
    press_any_key
}

# ============================================================================
# Status & Logs Functions
# ============================================================================

show_status() {
    print_banner
    print_header "Bot Status"
    
    echo -e "${WHITE}Systemd Service:${NC}"
    systemctl status $SERVICE_NAME --no-pager -l
    
    echo ""
    echo -e "${WHITE}Disk Usage:${NC}"
    df -h "$INSTALL_DIR" 2>/dev/null || df -h /
    
    echo ""
    echo -e "${WHITE}Memory Usage:${NC}"
    free -h
    
    press_any_key
}

show_logs() {
    print_banner
    print_header "Bot Logs"
    
    echo -e "${CYAN}Showing last 50 lines...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to exit${NC}"
    echo ""
    
    journalctl -u $SERVICE_NAME -n 50 --no-pager
    
    echo ""
    if confirm "Do you want to watch live logs?" "y"; then
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
            status_text="${GREEN}Running${NC}"
        else
            status_icon="${RED}●${NC}"
            status_text="${RED}Stopped${NC}"
        fi
        
        echo -e "  Bot Status: $status_icon $status_text"
        echo ""
        echo -e "${CYAN}╔════════════════════════════════════════════════════════════════════╗${NC}"
        echo -e "${CYAN}║${NC}                      ${BOLD}MAIN MENU${NC}                                    ${CYAN}║${NC}"
        echo -e "${CYAN}╠════════════════════════════════════════════════════════════════════╣${NC}"
        echo -e "${CYAN}║${NC}                                                                    ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}1.${NC} Install Bot ${YELLOW}(Fresh Install)${NC}                                ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}2.${NC} Uninstall Bot ${RED}(Remove all files)${NC}                          ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}3.${NC} Update Bot ${CYAN}(Pull latest version)${NC}                           ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}4.${NC} Start Bot                                                    ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}5.${NC} Stop Bot                                                     ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}6.${NC} Restart Bot                                                  ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}7.${NC} Bot Status ${BLUE}(Check service status)${NC}                          ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}8.${NC} View Logs                                                    ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}  ${GREEN}9.${NC} Backup ${MAGENTA}(Database & Config)${NC}                               ${CYAN}║${NC}"

        echo -e "${CYAN}║${NC}  ${GREEN}0.${NC} Exit                                                         ${CYAN}║${NC}"
        echo -e "${CYAN}║${NC}                                                                    ${CYAN}║${NC}"
        echo -e "${CYAN}╚════════════════════════════════════════════════════════════════════╝${NC}"
        echo ""
        
        echo -e -n "${YELLOW}Your choice ${WHITE}[0-9]${YELLOW}: ${NC}"
        read choice
        
        case $choice in
            1) install_bot ;;
            2) uninstall_bot ;;
            3) update_bot ;;
            4)
                print_step "Starting bot..."
                systemctl start $SERVICE_NAME
                sleep 1
                if systemctl is-active --quiet $SERVICE_NAME; then
                    print_success "Bot started"
                else
                    print_error "Error starting bot"
                fi
                press_any_key
                ;;
            5)
                print_step "Stopping bot..."
                systemctl stop $SERVICE_NAME
                sleep 1
                print_success "Bot stopped"
                press_any_key
                ;;
            6)
                print_step "Restarting bot..."
                systemctl restart $SERVICE_NAME
                sleep 2
                if systemctl is-active --quiet $SERVICE_NAME; then
                    print_success "Bot restarted"
                else
                    print_error "Error restarting bot"
                fi
                press_any_key
                ;;
            7) show_status ;;
            8) show_logs ;;
            9) backup_bot ;;

            0)
                clear
                echo -e "${GREEN}Goodbye! 👋${NC}"
                exit 0
                ;;
            *)
                print_error "Invalid option"
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
