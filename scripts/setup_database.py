#!/usr/bin/env python3
"""
CODM Attachments Bot - Database Setup Script
==============================================
This script creates a clean PostgreSQL database for the CODM bot.

Database: codm_attachments_db
User: codm_bot_user
Password: CoDM_Secure_2025!@#

Usage:
    python setup_database.py [--drop-existing]

Options:
    --drop-existing    Drop and recreate the database if it exists
"""

import sys
import os
import psycopg
from psycopg import sql
from pathlib import Path

# Configuration
DB_NAME = "codm_attachments_db"
DB_USER = "codm_bot_user"
DB_PASSWORD = "CoDM_Secure_2025!@#" 
DB_HOST = "localhost"
DB_PORT = 5432

# PostgreSQL superuser credentials (for creating database)
POSTGRES_USER = "postgres"
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")

# Colors for output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.ENDC}")

def print_info(msg):
    print(f"{Colors.BLUE}→ {msg}{Colors.ENDC}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.ENDC}")

def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.ENDC}")

def print_header(msg):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{msg}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.ENDC}\n")


def check_postgres_connection():
    """Check if we can connect to PostgreSQL"""
    print_info("Checking PostgreSQL connection...")
    try:
        conn = psycopg.connect(
            f"host={DB_HOST} port={DB_PORT} user={POSTGRES_USER} " +
            f"password={POSTGRES_PASSWORD} dbname=postgres",
            autocommit=True
        )
        conn.close()
        print_success("PostgreSQL connection OK")
        return True
    except Exception as e:
        print_error(f"Cannot connect to PostgreSQL: {e}")
        return False


def drop_database_if_exists():
    """Drop the database if it exists"""
    print_info(f"Dropping database '{DB_NAME}' if exists...")
    try:
        conn = psycopg.connect(
            f"host={DB_HOST} port={DB_PORT} user={POSTGRES_USER} " +
            f"password={POSTGRES_PASSWORD} dbname=postgres",
            autocommit=True
        )
        cur = conn.cursor()
        
        # Terminate existing connections
        cur.execute(sql.SQL("""
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid != pg_backend_pid()
        """), [DB_NAME])
        
        # Drop database
        cur.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(
            sql.Identifier(DB_NAME)
        ))
        
        cur.close()
        conn.close()
        print_success(f"Database '{DB_NAME}' dropped")
        return True
    except Exception as e:
        print_error(f"Error dropping database: {e}")
        return False


def create_database():
    """Create the database"""
    print_info(f"Creating database '{DB_NAME}'...")
    try:
        conn = psycopg.connect(
            f"host={DB_HOST} port={DB_PORT} user={POSTGRES_USER} " +
            f"password={POSTGRES_PASSWORD} dbname=postgres",
            autocommit=True
        )
        cur = conn.cursor()
        
        cur.execute(sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8'").format(
            sql.Identifier(DB_NAME),
            sql.Identifier(DB_USER)
        ))
        
        cur.close()
        conn.close()
        print_success(f"Database '{DB_NAME}' created")
        return True
    except Exception as e:
        print_error(f"Error creating database: {e}")
        return False


def run_setup_script():
    """Run the SQL setup script"""
    print_info("Running setup script...")
    
    script_path = Path(__file__).parent / "setup_database.sql"
    if not script_path.exists():
        print_error(f"Setup script not found: {script_path}")
        return False
    
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        conn = psycopg.connect(
            f"host={DB_HOST} port={DB_PORT} user={POSTGRES_USER} " +
            f"password={POSTGRES_PASSWORD} dbname={DB_NAME}"
        )
        cur = conn.cursor()
        
        # Execute the script
        cur.execute(sql_script)
        conn.commit()
        
        cur.close()
        conn.close()
        print_success("Setup script executed successfully")
        return True
    except Exception as e:
        print_error(f"Error running setup script: {e}")
        return False


def verify_setup():
    """Verify the database setup"""
    print_info("Verifying database setup...")
    try:
        conn = psycopg.connect(
            f"host={DB_HOST} port={DB_PORT} user={DB_USER} " +
            f"password={DB_PASSWORD} dbname={DB_NAME}"
        )
        cur = conn.cursor()
        
        # Count tables
        cur.execute("""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        table_count = cur.fetchone()[0]
        print_success(f"Tables created: {table_count}")
        
        # Check extensions
        cur.execute("SELECT extname FROM pg_extension WHERE extname IN ('pg_trgm', 'unaccent')")
        extensions = [row[0] for row in cur.fetchall()]
        print_success(f"Extensions: {', '.join(extensions)}")
        
        # Check categories
        cur.execute("SELECT COUNT(*) FROM weapon_categories")
        category_count = cur.fetchone()[0]
        print_success(f"Weapon categories: {category_count}")
        
        # Check roles
        cur.execute("SELECT COUNT(*) FROM roles")
        role_count = cur.fetchone()[0]
        print_success(f"Roles: {role_count}")
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print_error(f"Verification failed: {e}")
        return False


def update_env_file():
    """Update the .env file with new credentials"""
    print_info("Updating .env file...")
    try:
        env_path = Path(__file__).parent.parent / ".env"
        
        if not env_path.exists():
            print_warning(".env file not found, skipping update")
            return True
        
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Update database configuration
        new_lines = []
        for line in lines:
            if line.startswith('DATABASE_URL='):
                new_lines.append(
                    f'DATABASE_URL=postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}\n'
                )
            elif line.startswith('DB_NAME='):
                new_lines.append(f'DB_NAME={DB_NAME}\n')
            elif line.startswith('DB_USER='):
                new_lines.append(f'DB_USER={DB_USER}\n')
            elif line.startswith('DB_PASSWORD='):
                new_lines.append(f'DB_PASSWORD={DB_PASSWORD}\n')
            else:
                new_lines.append(line)
        
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        print_success(".env file updated")
        return True
    except Exception as e:
        print_warning(f"Could not update .env file: {e}")
        return True  # Non-critical


def main():
    """Main setup process"""
    print_header("CODM Attachments Bot - Database Setup")
    
    # Check arguments
    drop_existing = '--drop-existing' in sys.argv
    
    # Step 1: Check PostgreSQL connection
    if not check_postgres_connection():
        print_error("Setup aborted")
        return 1
    
    # Step 2: Drop existing database if requested
    if drop_existing:
        print_header("Dropping Existing Database")
        if not drop_database_if_exists():
            print_error("Setup aborted")
            return 1
    
    # Step 3: Create database
    print_header("Creating Database")
    if not create_database():
        print_warning("Database might already exist, continuing...")
    
    # Step 4: Run setup script
    print_header("Setting Up Tables")
    if not run_setup_script():
        print_error("Setup aborted")
        return 1
    
    # Step 5: Verify setup
    print_header("Verifying Setup")
    if not verify_setup():
        print_error("Setup verification failed")
        return 1
    
    # Step 6: Update .env file
    print_header("Updating Configuration")
    update_env_file()
    
    # Success!
    print_header("Setup Complete!")
    print_success(f"Database '{DB_NAME}' is ready to use")
    print_info(f"\nConnection Details:")
    print(f"  Host: {DB_HOST}")
    print(f"  Port: {DB_PORT}")
    print(f"  Database: {DB_NAME}")
    print(f"  User: {DB_USER}")
    print(f"  Password: {DB_PASSWORD}")
    print(f"\n{Colors.BLUE}You can now run: python main.py{Colors.ENDC}\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
