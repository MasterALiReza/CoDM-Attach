#!/bin/bash

# CODM Bot Deployment Script for Ubuntu 24.04
# This script installs dependencies, sets up the environment, and configures the bot as a systemd service.

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
  echo -e "${RED}Please run as root (sudo ./deploy.sh)${NC}"
  exit 1
fi

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}       CODM Bot Deployment Script (Ubuntu 24.04)  ${NC}"
echo -e "${BLUE}==================================================${NC}"

# 1. System Update & Dependencies
echo -e "\n${YELLOW}[1/6] Updating system and installing dependencies...${NC}"
apt update && apt upgrade -y
apt install -y python3-pip python3-venv postgresql postgresql-contrib git acl

# 2. Project Setup
echo -e "\n${YELLOW}[2/6] Setting up project directory...${NC}"
INSTALL_DIR="/opt/codm-bot"
BOT_USER="codm-bot"

# Create dedicated user if not exists
if id "$BOT_USER" &>/dev/null; then
    echo "User $BOT_USER already exists."
else
    useradd -r -m -s /bin/bash $BOT_USER
    echo "Created user $BOT_USER."
fi

# Create install directory
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR already exists. Updating contents..."
else
    mkdir -p $INSTALL_DIR
    echo "Created $INSTALL_DIR."
fi

# Copy files (assuming script is run from repo root)
echo "Copying files to $INSTALL_DIR..."
cp -r . "$INSTALL_DIR"
chown -R $BOT_USER:$BOT_USER "$INSTALL_DIR"

# 3. Python Environment
echo -e "\n${YELLOW}[3/6] Setting up Python virtual environment...${NC}"
cd "$INSTALL_DIR"

# Run as bot user to ensure permissions
sudo -u $BOT_USER python3 -m venv venv
sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
sudo -u $BOT_USER "$INSTALL_DIR/venv/bin/pip" install -r requirements.txt

echo -e "${GREEN}Python environment set up successfully.${NC}"

# 4. Database Setup (Interactive)
echo -e "\n${YELLOW}[4/6] Database Configuration...${NC}"
read -p "Do you want to install and configure a local PostgreSQL database? (y/n): " SETUP_DB

if [[ "$SETUP_DB" =~ ^[Yy]$ ]]; then
    echo "Configuring local PostgreSQL..."
    
    read -p "Enter database name (default: codm_db): " DB_NAME
    DB_NAME=${DB_NAME:-codm_db}
    
    read -p "Enter database user (default: codm_user): " DB_USER
    DB_USER=${DB_USER:-codm_user}
    
    read -s -p "Enter database password: " DB_PASS
    echo ""
    
    # Create User and DB
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" 2>/dev/null || echo "User might already exist."
    sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';"
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" 2>/dev/null || echo "Database might already exist."
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    
    # Construct DATABASE_URL
    DATABASE_URL="postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME"
    echo -e "${GREEN}Database configured locally.${NC}"
else
    read -p "Enter your existing PostgreSQL connection string (DATABASE_URL): " DATABASE_URL
fi

# 5. Environment Configuration (.env)
echo -e "\n${YELLOW}[5/6] Configuring Environment Variables...${NC}"

read -p "Enter Telegram Bot Token: " BOT_TOKEN
read -p "Enter Super Admin ID (Numeric Telegram ID): " SUPER_ADMIN_ID

cat > "$INSTALL_DIR/.env" <<EOF
BOT_TOKEN=$BOT_TOKEN
SUPER_ADMIN_ID=$SUPER_ADMIN_ID
DATABASE_URL=$DATABASE_URL
DEFAULT_LANG=fa
SUPPORTED_LANGS=fa,en
FALLBACK_LANG=en
DB_POOL_SIZE=20
DB_POOL_MAX_OVERFLOW=10
EOF

chown $BOT_USER:$BOT_USER "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"

echo -e "${GREEN}.env file created successfully.${NC}"

# 6. Systemd Service
echo -e "\n${YELLOW}[6/6] Creating Systemd Service...${NC}"

SERVICE_FILE="/etc/systemd/system/codm-bot.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=CODM Attachments Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=$BOT_USER
Group=$BOT_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=$INSTALL_DIR/.env

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable codm-bot

echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}Deployment Setup Complete!${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "To start the bot, run: ${YELLOW}systemctl start codm-bot${NC}"
echo -e "To check status, run: ${YELLOW}systemctl status codm-bot${NC}"
echo -e "To view logs, run: ${YELLOW}journalctl -u codm-bot -f${NC}"
echo -e "${BLUE}==================================================${NC}"
