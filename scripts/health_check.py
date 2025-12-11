#!/usr/bin/env python3
"""
CODM Bot Health Check Script
=============================
Quick health check utility for bot status verification.
Used by wx-attach CLI tool for detailed status checks.

Usage:
    python health_check.py [--json]
"""

import os
import sys
import json
from datetime import datetime

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Load environment
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, '.env'))


def check_database() -> dict:
    """Check PostgreSQL database connection."""
    result = {
        "name": "Database",
        "status": "unknown",
        "details": {}
    }
    
    try:
        import psycopg
        from psycopg.rows import dict_row
        
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            result["status"] = "error"
            result["details"]["error"] = "DATABASE_URL not configured"
            return result
        
        start_time = datetime.now()
        conn = psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row)
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        
        cur = conn.cursor()
        
        # Get PostgreSQL version
        cur.execute("SELECT version()")
        version = cur.fetchone()['version'].split(',')[0]
        
        # Count tables
        cur.execute("SELECT COUNT(*) as count FROM pg_tables WHERE schemaname = 'public'")
        tables_count = cur.fetchone()['count']
        
        # Check key tables exist
        key_tables = ['users', 'admins', 'weapons', 'attachments']
        cur.execute("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public' AND tablename = ANY(%s)
        """, (key_tables,))
        existing_tables = [row['tablename'] for row in cur.fetchall()]
        
        # Count data
        counts = {}
        for table in ['users', 'admins', 'attachments']:
            try:
                cur.execute(f"SELECT COUNT(*) as count FROM {table}")
                counts[table] = cur.fetchone()['count']
            except:
                counts[table] = -1
        
        conn.close()
        
        result["status"] = "ok"
        result["details"] = {
            "version": version,
            "tables_count": tables_count,
            "key_tables_ok": len(existing_tables) == len(key_tables),
            "response_time_ms": round(elapsed, 2),
            "record_counts": counts
        }
        
    except ImportError:
        result["status"] = "error"
        result["details"]["error"] = "psycopg not installed"
    except Exception as e:
        result["status"] = "error"
        result["details"]["error"] = str(e)
    
    return result


def check_telegram() -> dict:
    """Check Telegram Bot API connection."""
    result = {
        "name": "Telegram API",
        "status": "unknown",
        "details": {}
    }
    
    try:
        import requests
        
        bot_token = os.getenv('BOT_TOKEN')
        if not bot_token:
            result["status"] = "error"
            result["details"]["error"] = "BOT_TOKEN not configured"
            return result
        
        start_time = datetime.now()
        response = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getMe",
            timeout=10
        )
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                bot_info = data.get('result', {})
                result["status"] = "ok"
                result["details"] = {
                    "bot_id": bot_info.get('id'),
                    "bot_username": bot_info.get('username'),
                    "bot_name": bot_info.get('first_name'),
                    "response_time_ms": round(elapsed, 2)
                }
            else:
                result["status"] = "error"
                result["details"]["error"] = data.get('description', 'Unknown error')
        else:
            result["status"] = "error"
            result["details"]["error"] = f"HTTP {response.status_code}"
            
    except ImportError:
        result["status"] = "error"
        result["details"]["error"] = "requests not installed"
    except Exception as e:
        result["status"] = "error"
        result["details"]["error"] = str(e)
    
    return result


def check_environment() -> dict:
    """Check required environment variables."""
    result = {
        "name": "Environment",
        "status": "unknown",
        "details": {}
    }
    
    required_vars = ['BOT_TOKEN', 'DATABASE_URL', 'SUPER_ADMIN_ID']
    optional_vars = ['DEFAULT_LANG', 'DB_POOL_SIZE']
    
    missing = []
    configured = []
    
    for var in required_vars:
        if os.getenv(var):
            configured.append(var)
        else:
            missing.append(var)
    
    optional_status = {var: bool(os.getenv(var)) for var in optional_vars}
    
    result["status"] = "ok" if not missing else "error"
    result["details"] = {
        "required_configured": configured,
        "required_missing": missing,
        "optional_status": optional_status
    }
    
    return result


def check_files() -> dict:
    """Check required files exist."""
    result = {
        "name": "Files",
        "status": "unknown",
        "details": {}
    }
    
    required_files = [
        'main.py',
        'requirements.txt',
        '.env',
        'core/database/database_pg.py',
        'scripts/setup_database.sql'
    ]
    
    missing = []
    found = []
    
    for file in required_files:
        path = os.path.join(PROJECT_ROOT, file)
        if os.path.exists(path):
            found.append(file)
        else:
            missing.append(file)
    
    result["status"] = "ok" if not missing else "warning"
    result["details"] = {
        "found": found,
        "missing": missing
    }
    
    return result


def check_super_admin() -> dict:
    """Check if super admin is configured in database."""
    result = {
        "name": "Super Admin",
        "status": "unknown",
        "details": {}
    }
    
    try:
        import psycopg
        from psycopg.rows import dict_row
        
        super_admin_id = os.getenv('SUPER_ADMIN_ID')
        if not super_admin_id:
            result["status"] = "error"
            result["details"]["error"] = "SUPER_ADMIN_ID not configured"
            return result
        
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            result["status"] = "error"
            result["details"]["error"] = "DATABASE_URL not configured"
            return result
        
        conn = psycopg.connect(database_url, connect_timeout=5, row_factory=dict_row)
        cur = conn.cursor()
        
        # Check if super admin exists in admins table
        cur.execute("""
            SELECT a.user_id, a.is_active, u.username
            FROM admins a
            LEFT JOIN users u ON a.user_id = u.user_id
            WHERE a.user_id = %s
        """, (int(super_admin_id),))
        
        admin = cur.fetchone()
        conn.close()
        
        if admin:
            result["status"] = "ok"
            result["details"] = {
                "user_id": admin['user_id'],
                "username": admin.get('username'),
                "is_active": admin['is_active'],
                "in_database": True
            }
        else:
            result["status"] = "warning"
            result["details"] = {
                "user_id": int(super_admin_id),
                "in_database": False,
                "note": "Super admin will be added on first bot startup"
            }
            
    except Exception as e:
        result["status"] = "error"
        result["details"]["error"] = str(e)
    
    return result


def run_all_checks() -> dict:
    """Run all health checks and return combined result."""
    checks = [
        check_environment(),
        check_files(),
        check_database(),
        check_telegram(),
        check_super_admin()
    ]
    
    overall_status = "ok"
    for check in checks:
        if check["status"] == "error":
            overall_status = "error"
            break
        elif check["status"] == "warning" and overall_status == "ok":
            overall_status = "warning"
    
    return {
        "timestamp": datetime.now().isoformat(),
        "overall_status": overall_status,
        "checks": checks
    }


def print_human_readable(result: dict):
    """Print results in human-readable format."""
    status_icons = {
        "ok": "✅",
        "warning": "⚠️",
        "error": "❌",
        "unknown": "❓"
    }
    
    print("\n" + "=" * 60)
    print("         CODM Bot Health Check Report")
    print("=" * 60)
    print(f"\nTimestamp: {result['timestamp']}")
    print(f"Overall Status: {status_icons.get(result['overall_status'], '?')} {result['overall_status'].upper()}")
    print("\n" + "-" * 60)
    
    for check in result['checks']:
        icon = status_icons.get(check['status'], '?')
        print(f"\n{icon} {check['name']}: {check['status'].upper()}")
        
        details = check.get('details', {})
        if 'error' in details:
            print(f"   Error: {details['error']}")
        else:
            for key, value in details.items():
                if isinstance(value, dict):
                    print(f"   {key}:")
                    for k, v in value.items():
                        print(f"      {k}: {v}")
                elif isinstance(value, list):
                    print(f"   {key}: {', '.join(map(str, value)) if value else 'None'}")
                else:
                    print(f"   {key}: {value}")
    
    print("\n" + "=" * 60)


def main():
    """Main entry point."""
    output_json = '--json' in sys.argv
    
    result = run_all_checks()
    
    if output_json:
        print(json.dumps(result, indent=2))
    else:
        print_human_readable(result)
    
    # Exit code based on status
    if result['overall_status'] == 'error':
        sys.exit(1)
    elif result['overall_status'] == 'warning':
        sys.exit(0)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
