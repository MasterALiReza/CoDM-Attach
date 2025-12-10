"""
مدیریت کامل Backup, Import, Export برای PostgreSQL
"""

import os
import json
import shutil
from datetime import datetime
from typing import Dict, Any, Optional
import logging
import zipfile
import tempfile

logger = logging.getLogger(__name__)


class BackupManager:
    """مدیریت backup/restore/import/export"""
    
    def __init__(self, database_adapter):
        self.db = database_adapter
        self.backup_dir = "backups"
        self._ensure_backup_dir()
    
    def _ensure_backup_dir(self):
        """ایجاد دایرکتوری backup در صورت عدم وجود"""
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)
    
    def _get_pg_tool(self, tool_name: str) -> Optional[str]:
        """Find PostgreSQL client tool (pg_dump/pg_restore) with env override and fallbacks"""
        try:
            # 1) Explicit env var override: PG_DUMP_PATH / PG_RESTORE_PATH
            env_key = f"{tool_name.upper()}_PATH"
            explicit_path = os.getenv(env_key)
            if explicit_path and os.path.exists(explicit_path):
                return explicit_path
            
            # 2) Use PATH
            import shutil as _sh
            which_path = _sh.which(tool_name)
            if which_path:
                return which_path
            
            # 3) Common locations
            candidates = []
            if os.name == 'nt':
                # Windows typical install locations
                roots = [
                    r"C:\\Program Files\\PostgreSQL",
                    r"C:\\Program Files (x86)\\PostgreSQL",
                ]
                for root in roots:
                    if os.path.isdir(root):
                        for ver in sorted(os.listdir(root), reverse=True):
                            bin_path = os.path.join(root, ver, 'bin', f"{tool_name}.exe")
                            candidates.append(bin_path)
            else:
                # Unix-like
                for base in [
                    "/usr/bin", 
                    "/usr/local/bin", 
                    "/opt/homebrew/bin", 
                    "/opt/local/bin"
                ]:
                    candidates.append(os.path.join(base, tool_name))
            
            for path in candidates:
                if os.path.exists(path):
                    return path
            
            return None
        except Exception:
            return None
    
    def _get_timestamp(self) -> str:
        """دریافت timestamp برای نام‌گذاری فایل‌ها"""
        return datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # ========== Backup Operations ==========
    
    def create_full_backup(self) -> Optional[str]:
        """ایجاد backup کامل از PostgreSQL"""
        return self._backup_postgres()
    
    
    def _backup_postgres(self) -> Optional[str]:
        """Backup PostgreSQL database با pg_dump"""
        try:
            import subprocess
            
            timestamp = self._get_timestamp()
            backup_file = os.path.join(self.backup_dir, f"postgres_{timestamp}.dump")
            
            # دریافت DATABASE_URL از environment
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                logger.error("DATABASE_URL not set for PostgreSQL backup")
                return None
            
            # Resolve pg_dump path cross-platform
            pg_dump = self._get_pg_tool('pg_dump')
            if not pg_dump:
                logger.error("pg_dump command not found. Install PostgreSQL client tools or set PG_DUMP_PATH to the full path of pg_dump.")
                return None
            
            # استفاده از pg_dump با format custom (بهترین برای restore)
            cmd = [pg_dump, '-Fc', '-f', backup_file, db_url]
            
            logger.info("Starting PostgreSQL backup...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # Backup فایل‌های جانبی (channel stats, etc.)
                backup_subdir = os.path.join(self.backup_dir, f"pg_backup_{timestamp}")
                os.makedirs(backup_subdir)
                
                files_backed_up = [backup_file]
                
                # Create metadata
                metadata = {
                    "timestamp": timestamp,
                    "date": datetime.now().isoformat(),
                    "database_backend": "postgres",
                    "database_url": db_url.split('@')[-1] if '@' in db_url else "hidden",  # بدون password
                    "files": [os.path.basename(f) for f in files_backed_up]
                }
                
                metadata_file = os.path.join(backup_subdir, "metadata.json")
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                
                files_backed_up.append(metadata_file)
                
                # Create ZIP archive
                zip_file = os.path.join(self.backup_dir, f"pg_backup_{timestamp}.zip")
                with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for file in files_backed_up:
                        zf.write(file, os.path.basename(file))
                
                # Clean up
                shutil.rmtree(backup_subdir)
                if os.path.exists(backup_file):
                    os.remove(backup_file)  # حذف .dump چون در ZIP قرار گرفت
                
                logger.info(f"PostgreSQL backup created: {zip_file}")
                return zip_file
            else:
                logger.error(f"pg_dump failed: {result.stderr}")
                return None
                
        except FileNotFoundError:
            logger.error("pg_dump command not found. Install PostgreSQL client tools or set PG_DUMP_PATH.")
            return None
        except Exception as e:
            logger.error(f"Error creating PostgreSQL backup: {e}")
            return None
    
    def restore_postgres_backup(self, backup_file: str) -> bool:
        """بازیابی از PostgreSQL backup"""
        try:
            import subprocess
            
            if not os.path.exists(backup_file):
                logger.error(f"Backup file not found: {backup_file}")
                return False
            
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                logger.error("DATABASE_URL not set")
                return False
            
            # Resolve pg_restore path cross-platform
            pg_restore = self._get_pg_tool('pg_restore')
            if not pg_restore:
                logger.error("pg_restore command not found. Install PostgreSQL client tools or set PG_RESTORE_PATH to the full path of pg_restore.")
                return False
            
            # اگر zip است، extract کن
            if backup_file.endswith('.zip'):
                with tempfile.TemporaryDirectory() as temp_dir:
                    with zipfile.ZipFile(backup_file, 'r') as zf:
                        zf.extractall(temp_dir)
                    
                    # پیدا کردن فایل .dump
                    dump_files = [f for f in os.listdir(temp_dir) if f.endswith('.dump')]
                    if not dump_files:
                        logger.error("No .dump file found in backup")
                        return False
                    
                    dump_file = os.path.join(temp_dir, dump_files[0])
                    
                    # Restore با pg_restore
                    cmd = [pg_restore, '-d', db_url, '-c', '--if-exists', dump_file]
                    
                    logger.info("Starting PostgreSQL restore...")
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        logger.info("PostgreSQL restore completed successfully")
                        return True
                    else:
                        logger.error(f"pg_restore failed: {result.stderr}")
                        return False
            else:
                # فایل مستقیم .dump
                cmd = [pg_restore, '-d', db_url, '-c', '--if-exists', backup_file]
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info("PostgreSQL restore completed successfully")
                    return True
                else:
                    logger.error(f"pg_restore failed: {result.stderr}")
                    return False
                    
        except FileNotFoundError:
            logger.error("pg_restore command not found. Install PostgreSQL client tools or set PG_RESTORE_PATH.")
            return False
        except Exception as e:
            logger.error(f"Error restoring PostgreSQL backup: {e}")
            return False
    
    def restore_from_backup(self, backup_file: str) -> bool:
        """بازیابی از فایل backup"""
        try:
            if not os.path.exists(backup_file):
                logger.error(f"Backup file not found: {backup_file}")
                return False
            
            # Extract to temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                with zipfile.ZipFile(backup_file, 'r') as zf:
                    zf.extractall(temp_dir)
                
                # Read metadata
                metadata_file = os.path.join(temp_dir, "metadata.json")
                if os.path.exists(metadata_file):
                    with open(metadata_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                    logger.info(f"Restoring from backup: {metadata['date']}")
                
                # Create safety backup before restore
                self.create_full_backup()
                
                # Restore files
                restored = False
                
                # Restore JSON backups by importing into PostgreSQL (no local JSON DB file)
                json_files = [f for f in os.listdir(temp_dir) if f.startswith("json_")]
                if json_files:
                    json_path = os.path.join(temp_dir, json_files[0])
                    try:
                        # Import JSON data into PostgreSQL and merge to avoid overwriting
                        self.import_from_json(json_path, merge=True)
                        logger.info("JSON backup imported into PostgreSQL")
                        restored = True
                    except Exception as e:
                        logger.error(f"Failed to import JSON backup into PostgreSQL: {e}")
                
                # NOTE: SQLite restore removed - PostgreSQL only
                # Old SQLite backups are no longer supported
                
                # Removed runtime JSON restores (stats/subscribers). All data resides in PostgreSQL now.
                
                return restored
                
        except Exception as e:
            logger.error(f"Error restoring backup: {e}")
            return False
    
    # ========== Export Operations ==========
    
    def export_to_json(self, output_file: str = None) -> Optional[str]:
        """Export تمام دیتا به فرمت JSON"""
        try:
            if output_file is None:
                output_file = os.path.join(self.backup_dir, f"export_{self._get_timestamp()}.json")
            
            export_data = {
                "metadata": {
                    "exported_at": datetime.now().isoformat(),
                    "database_mode": self.db.mode.value,
                    "version": "2.0"
                },
                "data": {
                    "weapons": {},
                    "guides": {},
                    "channels": [],
                    "users": []
                }
            }
            
            # Export weapons and attachments
            categories = ['assault_rifle', 'smg', 'lmg', 'sniper', 'marksman', 'shotgun', 'pistol', 'launcher']
            for category in categories:
                export_data["data"]["weapons"][category] = {}
                weapons = self.db.get_weapons_in_category(category)
                
                for weapon in weapons:
                    export_data["data"]["weapons"][category][weapon] = {
                        "br": {
                            "top_attachments": [],
                            "all_attachments": []
                        },
                        "mp": {
                            "top_attachments": [],
                            "all_attachments": []
                        }
                    }
                    
                    for mode in ['br', 'mp']:
                        # Get top attachments
                        top_atts = self.db.get_top_attachments(category, weapon, mode)
                        export_data["data"]["weapons"][category][weapon][mode]["top_attachments"] = top_atts
                        
                        # Get all attachments
                        all_atts = self.db.get_all_attachments(category, weapon, mode)
                        export_data["data"]["weapons"][category][weapon][mode]["all_attachments"] = all_atts
            
            # Export guides
            for mode in ['br', 'mp']:
                guides = self.db.get_guides(mode)
                export_data["data"]["guides"][mode] = guides
            
            # Export channels
            channels = self.db.get_required_channels()
            export_data["data"]["channels"] = channels
            
            # Export users (if available)
            try:
                users = self.db.get_all_users()
                export_data["data"]["users"] = users
            except Exception as e:
                logger.warning(f"Failed to export users data: {e}")
            
            # Save to file
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Data exported to: {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Error exporting data: {e}")
            return None
    
    def export_to_csv(self, output_dir: str = None) -> Optional[str]:
        """Export دیتا به فرمت CSV"""
        try:
            import csv
            
            if output_dir is None:
                output_dir = os.path.join(self.backup_dir, f"csv_export_{self._get_timestamp()}")
            
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # Export weapons
            weapons_file = os.path.join(output_dir, "weapons.csv")
            with open(weapons_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Category', 'Weapon', 'Mode', 'Attachment_Code', 'Attachment_Name', 'Is_Top', 'Is_Season_Top'])
                
                categories = ['assault_rifle', 'smg', 'lmg', 'sniper', 'marksman', 'shotgun', 'pistol', 'launcher']
                for category in categories:
                    weapons = self.db.get_weapons_in_category(category)
                    for weapon in weapons:
                        for mode in ['br', 'mp']:
                            all_atts = self.db.get_all_attachments(category, weapon, mode)
                            top_atts = self.db.get_top_attachments(category, weapon, mode)
                            top_codes = {att['code'] for att in top_atts}
                            
                            for att in all_atts:
                                writer.writerow([
                                    category,
                                    weapon,
                                    mode,
                                    att.get('code', ''),
                                    att.get('name', ''),
                                    att['code'] in top_codes,
                                    att.get('season_top', False)
                                ])
            
            # Export channels
            channels_file = os.path.join(output_dir, "channels.csv")
            with open(channels_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Channel_ID', 'Title', 'URL'])
                
                channels = self.db.get_required_channels()
                for ch in channels:
                    writer.writerow([ch.get('channel_id'), ch.get('title'), ch.get('url')])
            
            logger.info(f"CSV export created in: {output_dir}")
            return output_dir
            
        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            return None
    
    # ========== Import Operations ==========
    
    def import_from_json(self, import_file: str, merge: bool = False) -> bool:
        """Import دیتا از فایل JSON"""
        try:
            if not os.path.exists(import_file):
                logger.error(f"Import file not found: {import_file}")
                return False
            
            # Create backup before import
            backup_file = self.create_full_backup()
            logger.info(f"Safety backup created: {backup_file}")
            
            with open(import_file, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Check format
            if 'data' in import_data:
                data = import_data['data']
            else:
                # Old format compatibility
                data = import_data
            
            imported_count = 0
            
            # Import weapons and attachments
            if 'weapons' in data:
                for category, weapons in data['weapons'].items():
                    if not isinstance(weapons, dict):
                        continue
                    
                    for weapon_name, weapon_data in weapons.items():
                        # Add weapon if not exists
                        self.db.add_weapon(category, weapon_name)
                        
                        # Process modes
                        if 'br' in weapon_data or 'mp' in weapon_data:
                            # New format with modes
                            for mode in ['br', 'mp']:
                                if mode not in weapon_data:
                                    continue
                                
                                mode_data = weapon_data[mode]
                                
                                # Import all attachments
                                if 'all_attachments' in mode_data:
                                    for att in mode_data['all_attachments']:
                                        if isinstance(att, dict):
                                            self.db.add_attachment(
                                                category, weapon_name,
                                                att.get('code', ''),
                                                att.get('name', ''),
                                                att.get('image'),
                                                False,  # is_top will be set later
                                                att.get('season_top', False),
                                                mode
                                            )
                                            imported_count += 1
                                
                                # Set top attachments
                                if 'top_attachments' in mode_data:
                                    top_codes = []
                                    for att in mode_data['top_attachments']:
                                        if isinstance(att, dict):
                                            top_codes.append(att.get('code', ''))
                                    if top_codes:
                                        self.db.set_top_attachments(category, weapon_name, top_codes, mode)
                        else:
                            # Old format without modes (assume BR)
                            if 'all_attachments' in weapon_data:
                                for att in weapon_data['all_attachments']:
                                    if isinstance(att, dict):
                                        self.db.add_attachment(
                                            category, weapon_name,
                                            att.get('code', ''),
                                            att.get('name', ''),
                                            att.get('image'),
                                            False,
                                            att.get('season_top', False),
                                            'br'
                                        )
                                        imported_count += 1
                            
                            if 'top_attachments' in weapon_data:
                                top_codes = []
                                for att in weapon_data['top_attachments']:
                                    if isinstance(att, dict):
                                        top_codes.append(att.get('code', ''))
                                if top_codes:
                                    self.db.set_top_attachments(category, weapon_name, top_codes, 'br')
            
            # Import channels
            if 'channels' in data:
                for ch in data['channels']:
                    if isinstance(ch, dict):
                        self.db.add_required_channel(
                            ch.get('channel_id', ''),
                            ch.get('title', ''),
                            ch.get('url', '')
                        )
            
            logger.info(f"Import completed: {imported_count} attachments imported")
            return True
            
        except Exception as e:
            logger.error(f"Error importing data: {e}")
            return False
    
    def list_backups(self) -> list:
        """لیست تمام backup های موجود"""
        backups = []
        
        if not os.path.exists(self.backup_dir):
            return backups
        
        for file in os.listdir(self.backup_dir):
            if file.endswith('.zip'):
                file_path = os.path.join(self.backup_dir, file)
                file_stat = os.stat(file_path)
                backups.append({
                    'filename': file,
                    'path': file_path,
                    'size': file_stat.st_size,
                    'created': datetime.fromtimestamp(file_stat.st_ctime).isoformat()
                })
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x['created'], reverse=True)
        return backups
    
    def cleanup_old_backups(self, keep_count: int = 10):
        """حذف backup های قدیمی و نگه داشتن تعداد محدود"""
        backups = self.list_backups()
        
        if len(backups) > keep_count:
            for backup in backups[keep_count:]:
                try:
                    os.remove(backup['path'])
                    logger.info(f"Old backup removed: {backup['filename']}")
                except Exception as e:
                    logger.error(f"Error removing old backup: {e}")
