"""
Data Health Check Script
Performs comprehensive validation of database content and quality
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logger import get_logger

if TYPE_CHECKING:
    from core.database.database_adapter import DatabaseAdapter

logger = get_logger('data_health_check', 'health_checks.log')

class DataHealthChecker:
    """Main class for checking data health and quality"""
    
    def __init__(self, db_adapter: 'DatabaseAdapter' = None, auto_fix=False):
        """
        Initialize health checker
        
        Args:
            db_adapter: DatabaseAdapter instance (اگر None باشد، یک instance جدید می‌سازد)
            auto_fix: If True, automatically fix simple issues (dangerous!)
        """
        # Initialize DatabaseAdapter (PostgreSQL-only in this project)
        if db_adapter is None:
            from core.database.database_adapter import DatabaseAdapter
            self.db = DatabaseAdapter()
        else:
            self.db = db_adapter
        # Optional path for reporting (PostgreSQL may expose db_path as DSN part)
        self.db_path = getattr(self.db, 'db_path', None)
        self.auto_fix = auto_fix
        self.issues = defaultdict(list)
        self.metrics = {}
        
    def _get(self, row, key_or_idx, default=None):
        """Return a value from a dict_row (psycopg3 row_factory=dict_row)."""
        if row is None:
            return default
        if isinstance(key_or_idx, str):
            return row.get(key_or_idx, default)
        # numeric index from mapping values (best-effort)
        try:
            return list(row.values())[key_or_idx]
        except Exception:
            return default
        
    def connect(self):
        """Get database connection context manager from pool"""
        if hasattr(self.db, 'get_connection'):
            return self.db.get_connection()
        raise RuntimeError("Database connection not available through adapter")
        
    def check_missing_images(self) -> List[Dict]:
        """Check for attachments without images"""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    a.id,
                    a.code,
                    a.name,
                    w.name as weapon,
                    wc.name as category
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories wc ON w.category_id = wc.id
                WHERE a.image_file_id IS NULL OR a.image_file_id = ''
                ORDER BY wc.name, w.name, a.name
            """)
            
            missing_images = []
            for row in cursor.fetchall():
                rid = self._get(row, 'id')
                code = self._get(row, 'code')
                name = self._get(row, 'name')
                weapon = self._get(row, 'weapon')
                category = self._get(row, 'category')
                missing_images.append({
                    'id': rid,
                    'code': code,
                    'name': name,
                    'weapon': weapon,
                    'category': category,
                    'issue': 'missing_image'
                })
                
            if missing_images:
                self.issues['CRITICAL'].append({
                    'type': 'missing_images',
                    'count': len(missing_images),
                    'details': missing_images
                })
                logger.warning(f"⚠️ Found {len(missing_images)} attachments without images")
            else:
                logger.info("✅ All attachments have images")
                
            return missing_images
        finally:
            pass
            
    def check_duplicate_codes(self) -> List[Dict]:
        """Check for duplicate attachment codes within same weapon"""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    w.name as weapon,
                    a.code,
                    COUNT(*) as count,
                    STRING_AGG(a.name, ', ') as names,
                    STRING_AGG(a.id::text, ', ') as ids
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                GROUP BY w.name, a.code
                HAVING COUNT(*) > 1
            """)
            
            duplicates = []
            for row in cursor.fetchall():
                weapon = self._get(row, 'weapon')
                code = self._get(row, 'code')
                cnt = self._get(row, 'count')
                names = self._get(row, 'names')
                ids = self._get(row, 'ids')
                duplicates.append({
                    'weapon': weapon,
                    'weapon_name': weapon,
                    'code': code,
                    'count': cnt,
                    'attachment_names': names,
                    'attachment_ids': ids,
                    'issue': 'duplicate_code'
                })
                
            if duplicates:
                self.issues['CRITICAL'].append({
                    'type': 'duplicate_codes',
                    'count': len(duplicates),
                    'details': duplicates
                })
                logger.warning(f"⚠️ Found {len(duplicates)} duplicate codes")
            else:
                logger.info("✅ No duplicate codes found")
                
            return duplicates
        finally:
            pass
            
    def check_empty_weapons(self) -> List[Dict]:
        """Check for weapons without any attachments"""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    w.id,
                    w.name,
                    wc.name as category
                FROM weapons w
                JOIN weapon_categories wc ON w.category_id = wc.id
                LEFT JOIN attachments a ON a.weapon_id = w.id
                WHERE a.id IS NULL
                ORDER BY wc.name, w.name
            """)
            
            empty_weapons = []
            for row in cursor.fetchall():
                wid = self._get(row, 'id')
                name = self._get(row, 'name')
                category = self._get(row, 'category')
                empty_weapons.append({
                    'id': wid,
                    'name': name,
                    'category': category,
                    'issue': 'no_attachments'
                })
                
            if empty_weapons:
                # Respect policy: ignore (default), info, warning, critical
                pol = getattr(self, 'policy_empty_weapons', 'ignore')
                if pol == 'ignore':
                    logger.info(f"ℹ️ Empty weapons found but ignored by policy: {len(empty_weapons)}")
                else:
                    sev = 'INFO' if pol == 'info' else ('WARNING' if pol == 'warning' else 'CRITICAL')
                    self.issues[sev].append({
                        'type': 'empty_weapons',
                        'count': len(empty_weapons),
                        'details': empty_weapons
                    })
                    logger.warning(f"⚠️ Empty weapons reported with severity={sev}: {len(empty_weapons)}")
            else:
                logger.info("✅ All weapons have attachments (or policy ignores check)")
                
            return empty_weapons
        finally:
            pass
            
    def check_required_indexes(self):
        """Verify presence of required indexes and extensions (read-only)."""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                # pg_trgm extension check (best-effort)
                try:
                    cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'")
                    has_trgm = cursor.fetchone() is not None
                except Exception:
                    has_trgm = False
                # Collect existing index names
                cursor.execute("""
                    SELECT indexname FROM pg_indexes 
                    WHERE schemaname = current_schema()
                """)
                rows = cursor.fetchall() or []
                idx_names = set([r.get('indexname') for r in rows])
                required = {
                    'idx_attachments_name_trgm',
                    'idx_attachments_code_trgm',
                    'ux_attachments_weapon_mode_code',
                    'ix_attachments_weapon_mode',
                    'ux_suggested_attachment_mode',
                    'ix_suggested_mode',
                    'ix_uae_attachment_id',
                    'ix_uae_attachment_id_rating',
                    'ix_ticket_attachments_ticket_id',
                    'ix_ticket_attachments_reply_id',
                }
                missing = [i for i in required if i not in idx_names]
                # Record issues
                det = {'type': 'missing_indexes', 'count': len(missing) + (0 if has_trgm else 1)}
                details = []
                if not has_trgm:
                    details.append({'extension': 'pg_trgm'})
                for i in missing:
                    details.append({'index': i})
                if details:
                    det['details'] = details
                    self.issues['WARNING'].append(det)
        finally:
            pass

    def check_sequences_synced(self):
        """Check that sequences for id columns are present/synced."""
        tables = ['data_quality_metrics', 'data_health_checks']
        try:
            with self.connect() as conn:
                try:
                    conn.autocommit = True
                except Exception:
                    pass
                cursor = conn.cursor()
                for tbl in tables:
                    # Get serial sequence name
                    cursor.execute("SELECT pg_get_serial_sequence(%s, 'id') as seq", (tbl,))
                    row = cursor.fetchone()
                    seq = row.get('seq') if row else None
                    if not seq:
                        self.issues['WARNING'].append({
                            'type': 'sequence_missing',
                            'table': tbl,
                            'count': 1,
                        })
                        continue
                    # last_value
                    try:
                        cursor.execute(f"SELECT last_value FROM {seq}::regclass")
                        lv_row = cursor.fetchone()
                        last_val = lv_row.get('last_value') if lv_row else 0
                    except Exception:
                        last_val = 0
                        try:
                            conn.rollback()
                        except Exception:
                            pass
                    # max(id)
                    cursor.execute(f"SELECT COALESCE(MAX(id),0) FROM {tbl}")
                    max_row = cursor.fetchone()
                    # psycopg may name the column 'coalesce' or provide an unnamed key; prefer first value
                    max_id = max_row.get('coalesce') if max_row and 'coalesce' in max_row else (list(max_row.values())[0] if max_row else 0)
                    if last_val < max_id:
                        self.issues['WARNING'].append({
                            'type': 'sequence_desync',
                            'table': tbl,
                            'details': {'last_value': last_val, 'max_id': max_id},
                            'count': 1,
                        })
        finally:
            pass

    def check_schema_columns(self):
        """Ensure required columns exist for core features."""
        required = {
            'attachments': ['updated_at', 'order_index'],
            'user_attachment_engagement': ['rating', 'total_views', 'total_clicks', 'first_view_date', 'last_view_date', 'feedback'],
        }
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                missing = []
                for table, cols in required.items():
                    for col in cols:
                        cursor.execute(
                            """
                            SELECT 1 FROM information_schema.columns
                            WHERE table_schema = current_schema() AND table_name = %s AND column_name = %s
                            """,
                            (table, col),
                        )
                        if cursor.fetchone() is None:
                            missing.append({'table': table, 'column': col})
                if missing:
                    self.issues['CRITICAL'].append({
                        'type': 'missing_columns',
                        'count': len(missing),
                        'details': missing,
                    })
        finally:
            pass
            
    def check_sparse_weapons(self) -> List[Dict]:
        """Check for weapons with very few attachments (<3)"""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    w.name as weapon,
                    wc.name as category,
                    COUNT(a.id) as attachment_count
                FROM weapons w
                JOIN weapon_categories wc ON w.category_id = wc.id
                LEFT JOIN attachments a ON a.weapon_id = w.id
                GROUP BY w.id, w.name, wc.name
                HAVING COUNT(a.id) BETWEEN 1 AND 2
                ORDER BY attachment_count ASC, wc.name, w.name
            """)
            
            sparse_weapons = []
            for row in cursor.fetchall():
                name = self._get(row, 'weapon')
                category = self._get(row, 'category')
                att_cnt = self._get(row, 'attachment_count')
                sparse_weapons.append({
                    'name': name,
                    'category': category,
                    'attachment_count': att_cnt,
                    'issue': 'too_few_attachments'
                })
                
            if sparse_weapons:
                self.issues['WARNING'].append({
                    'type': 'sparse_weapons',
                    'count': len(sparse_weapons),
                    'details': sparse_weapons
                })
                logger.info(f"ℹ️ Found {len(sparse_weapons)} weapons with <3 attachments")
                
            return sparse_weapons
        finally:
            pass
            
    def check_orphaned_attachments(self) -> List[Dict]:
        """Check for attachments pointing to non-existent weapons"""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    a.id,
                    a.code,
                    a.name,
                    a.weapon_id
                FROM attachments a
                LEFT JOIN weapons w ON a.weapon_id = w.id
                WHERE w.id IS NULL
            """)
            
            orphaned = []
            for row in cursor.fetchall():
                rid = self._get(row, 'id')
                code = self._get(row, 'code')
                name = self._get(row, 'name')
                weapon_id = self._get(row, 'weapon_id')
                orphaned.append({
                    'id': rid,
                    'code': code,
                    'name': name,
                    'weapon_id': weapon_id,
                    'issue': 'orphaned_attachment'
                })
                
            if orphaned:
                self.issues['CRITICAL'].append({
                    'type': 'orphaned_attachments',
                    'count': len(orphaned),
                    'details': orphaned
                })
                logger.error(f"❌ Found {len(orphaned)} orphaned attachments!")
            else:
                logger.info("✅ No orphaned attachments found")
                
            return orphaned
        finally:
            pass
            
    def check_data_freshness(self) -> Dict:
        """Check how recently data was updated"""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                # Check last attachment added/modified
                cursor.execute("""
                SELECT 
                    MAX(created_at) as last_created
                FROM attachments
                WHERE created_at IS NOT NULL
            """)
                row = cursor.fetchone()
                last_created = self._get(row, 'last_created')
                
                if last_created:
                    if isinstance(last_created, str):
                        last_date = datetime.fromisoformat(last_created)
                    else:
                        last_date = last_created
                    days_old = (datetime.now() - last_date).days
                    
                    if days_old > 30:
                        self.issues['INFO'].append({
                            'type': 'stale_data',
                            'days_old': days_old,
                            'last_update': str(last_date)
                        })
                        logger.info(f"ℹ️ Data is {days_old} days old")
                else:
                    logger.info("ℹ️ No timestamp data available")
        finally:
            pass
            
    def calculate_metrics(self) -> Dict:
        """Calculate overall data quality metrics"""
        try:
            with self.connect() as conn:
                cursor = conn.cursor()
                metrics = {}
                
                # Basic counts
                cursor.execute("SELECT COUNT(*) as cnt FROM weapon_categories")
                metrics['total_categories'] = self._get(cursor.fetchone(), 'cnt')
                
                cursor.execute("SELECT COUNT(*) as cnt FROM weapons")
                metrics['total_weapons'] = self._get(cursor.fetchone(), 'cnt')
                
                cursor.execute("SELECT COUNT(*) as cnt FROM attachments")
                metrics['total_attachments'] = self._get(cursor.fetchone(), 'cnt')
                
                # Attachment distribution
                cursor.execute("""
                SELECT 
                    wc.name as category,
                    COUNT(DISTINCT w.id) as weapon_count,
                    COUNT(a.id) as attachment_count
                FROM weapon_categories wc
                LEFT JOIN weapons w ON w.category_id = wc.id
                LEFT JOIN attachments a ON a.weapon_id = w.id
                GROUP BY wc.id, wc.name
                ORDER BY wc.name
            """)
            
                metrics['category_distribution'] = []
                for row in cursor.fetchall():
                    category = self._get(row, 'category')
                    weapons = self._get(row, 'weapon_count')
                    attachments = self._get(row, 'attachment_count')
                    metrics['category_distribution'].append({
                        'category': category,
                        'weapons': weapons,
                        'attachments': attachments
                    })

                # Top/Season statistics (PostgreSQL booleans)
                cursor.execute("SELECT COUNT(*) as cnt FROM attachments WHERE is_top = TRUE")
                metrics['top_attachments'] = self._get(cursor.fetchone(), 'cnt', default=0)
                
                cursor.execute("SELECT COUNT(*) as cnt FROM attachments WHERE is_season_top = TRUE")
                metrics['season_attachments'] = self._get(cursor.fetchone(), 'cnt', default=0)
                
                cursor.execute("SELECT COUNT(*) as cnt FROM attachments WHERE image_file_id IS NOT NULL AND image_file_id != ''")
                with_images = self._get(cursor.fetchone(), 'cnt', default=0)
                metrics['attachments_with_images'] = with_images
                metrics['attachments_without_images'] = metrics['total_attachments'] - with_images
                metrics['image_coverage'] = (with_images / metrics['total_attachments'] * 100) if metrics['total_attachments'] > 0 else 0
                
                self.metrics = metrics
                return metrics
        finally:
            pass
            
    def save_results(self) -> int:
        """Save health check results to database"""
        try:
            with self.db.transaction() as tconn:
                cursor = tconn.cursor()
                check_id = None
                
                # Save each issue category
                for severity, issues_list in self.issues.items():
                    for issue in issues_list:
                        if check_id is None:
                            cursor.execute(
                                """
                                INSERT INTO data_health_checks (
                                    check_type, severity, category, 
                                    issue_count, details
                                ) VALUES (%s, %s, %s, %s, %s)
                                RETURNING id
                                """,
                                (
                                    issue['type'],
                                    severity,
                                    issue.get('category', 'general'),
                                    issue.get('count', 0),
                                    json.dumps(issue, ensure_ascii=False),
                                ),
                            )
                            row = cursor.fetchone()
                            check_id = self._get(row, 'id')
                        else:
                            cursor.execute(
                                """
                                INSERT INTO data_health_checks (
                                    check_type, severity, category, 
                                    issue_count, details
                                ) VALUES (%s, %s, %s, %s, %s)
                                """,
                                (
                                    issue['type'],
                                    severity,
                                    issue.get('category', 'general'),
                                    issue.get('count', 0),
                                    json.dumps(issue, ensure_ascii=False),
                                ),
                            )
                
                # Save quality metrics
                if self.metrics:
                    # Compute empty weapons count across severities
                    empty_weapons_count = 0
                    for sev in ('CRITICAL', 'WARNING'):
                        for it in self.issues.get(sev, []):
                            if it.get('type') == 'empty_weapons':
                                empty_weapons_count += int(it.get('count', 0))
                    total_weapons = int(self.metrics.get('total_weapons', 0))
                    total_attachments = int(self.metrics.get('total_attachments', 0))
                    image_coverage = float(self.metrics.get('image_coverage', 0))
                    with_images = int(total_attachments * image_coverage / 100)
                    without_images = int(total_attachments * (100 - image_coverage) / 100)
                    weapons_with_attachments = max(0, total_weapons - empty_weapons_count)
                    weapons_without_attachments = max(0, empty_weapons_count)
                    try:
                        cursor.execute(
                            """
                            INSERT INTO data_quality_metrics (
                                total_weapons, total_attachments,
                                weapons_with_attachments, weapons_without_attachments,
                                attachments_with_images, attachments_without_images,
                                health_score
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                total_weapons,
                                total_attachments,
                                weapons_with_attachments,
                                weapons_without_attachments,
                                with_images,
                                without_images,
                                self.calculate_health_score(),
                            ),
                        )
                    except Exception as insert_err:
                        # Attempt to sync sequence if PK duplicate arises, then retry once
                        try:
                            cursor.execute(
                                """
                                SELECT setval(
                                  pg_get_serial_sequence('data_quality_metrics','id'),
                                  COALESCE((SELECT MAX(id) FROM data_quality_metrics), 0) + 1,
                                  false
                                )
                                """
                            )
                            cursor.execute(
                                """
                                INSERT INTO data_quality_metrics (
                                    total_weapons, total_attachments,
                                    weapons_with_attachments, weapons_without_attachments,
                                    attachments_with_images, attachments_without_images,
                                    health_score
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                                """,
                                (
                                    total_weapons,
                                    total_attachments,
                                    weapons_with_attachments,
                                    weapons_without_attachments,
                                    with_images,
                                    without_images,
                                    self.calculate_health_score(),
                                ),
                            )
                        except Exception as retry_err:
                            raise retry_err
            logger.info(f"✅ Results saved to database (Check ID: {check_id})")
            return check_id
        except Exception as e:
            logger.error(f"❌ Error saving results: {e}")
            return None
            
    def calculate_health_score(self) -> float:
        """Calculate overall health score (0-100)"""
        score = 100.0
        
        # Deduct for critical issues
        critical_count = sum(issue.get('count', 0) for issue in self.issues.get('CRITICAL', []))
        score -= min(critical_count * 5, 50)  # Max 50 point deduction
        
        # Deduct for warnings
        warning_count = sum(issue.get('count', 0) for issue in self.issues.get('WARNING', []))
        score -= min(warning_count * 2, 30)  # Max 30 point deduction
        
        # Deduct for poor image coverage
        image_coverage = self.metrics.get('image_coverage', 100)
        if image_coverage < 80:
            score -= (80 - image_coverage) / 2  # Max 40 point deduction
            
        return max(0, score)
        
    def generate_report(self, format='text') -> str:
        """Generate human-readable report"""
        if format == 'text':
            return self._generate_text_report()
        elif format == 'markdown':
            return self._generate_markdown_report()
        else:
            raise ValueError(f"Unknown format: {format}")
            
    def _generate_text_report(self) -> str:
        """Generate plain text report"""
        lines = []
        lines.append("=" * 50)
        lines.append("📊 DATA HEALTH CHECK REPORT")
        lines.append("=" * 50)
        lines.append(f"🗓️ Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        db_label = os.path.basename(self.db_path) if self.db_path else 'PostgreSQL'
        lines.append(f"📁 Database: {db_label}")
        lines.append("")
        
        # Summary metrics
        lines.append("📈 SUMMARY METRICS:")
        lines.append(f"  • Total Categories: {self.metrics.get('total_categories', 0)}")
        lines.append(f"  • Total Weapons: {self.metrics.get('total_weapons', 0)}")
        lines.append(f"  • Total Attachments: {self.metrics.get('total_attachments', 0)}")
        lines.append(f"  • Image Coverage: {self.metrics.get('image_coverage', 0):.1f}%")
        lines.append(f"  • Top Attachments: {self.metrics.get('top_attachments', 0)}")
        lines.append(f"  • Season Best: {self.metrics.get('season_attachments', 0)}")
        lines.append("")
        
        # Issues by severity
        for severity in ['CRITICAL', 'WARNING', 'INFO']:
            if severity in self.issues:
                lines.append(f"{'❌' if severity == 'CRITICAL' else '⚠️' if severity == 'WARNING' else 'ℹ️'} {severity} ISSUES:")
                for issue in self.issues[severity]:
                    lines.append(f"  • {issue['type']}: {issue.get('count', 0)} found")
                lines.append("")
                
        # Health score
        score = self.calculate_health_score()
        emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        lines.append(f"{emoji} HEALTH SCORE: {score:.1f}/100")
        lines.append("=" * 50)
        
        return "\n".join(lines)
        
    def _generate_markdown_report(self) -> str:
        """Generate markdown report"""
        lines = []
        lines.append("# 📊 Data Health Check Report")
        lines.append("")
        lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        db_label = os.path.basename(self.db_path) if self.db_path else 'PostgreSQL'
        lines.append(f"**Database:** `{db_label}`")
        lines.append("")
        
        # Summary metrics
        lines.append("## 📈 Summary Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Categories | {self.metrics.get('total_categories', 0)} |")
        lines.append(f"| Total Weapons | {self.metrics.get('total_weapons', 0)} |")
        lines.append(f"| Total Attachments | {self.metrics.get('total_attachments', 0)} |")
        lines.append(f"| Image Coverage | {self.metrics.get('image_coverage', 0):.1f}% |")
        lines.append(f"| Top Attachments | {self.metrics.get('top_attachments', 0)} |")
        lines.append(f"| Season Best | {self.metrics.get('season_attachments', 0)} |")
        lines.append("")
        
        # Category distribution
        if self.metrics.get('category_distribution'):
            lines.append("## 📦 Category Distribution")
            lines.append("")
            lines.append("| Category | Weapons | Attachments |")
            lines.append("|----------|---------|-------------|")
            for cat in self.metrics['category_distribution']:
                lines.append(f"| {cat['category']} | {cat['weapons']} | {cat['attachments']} |")
            lines.append("")
            
        # Issues
        lines.append("## 🔍 Issues Found")
        lines.append("")
        
        for severity in ['CRITICAL', 'WARNING', 'INFO']:
            if severity in self.issues:
                emoji = "❌" if severity == "CRITICAL" else "⚠️" if severity == "WARNING" else "ℹ️"
                lines.append(f"### {emoji} {severity}")
                lines.append("")
                for issue in self.issues[severity]:
                    lines.append(f"- **{issue['type']}**: {issue.get('count', 0)} found")
                lines.append("")
                
        # Health score
        score = self.calculate_health_score()
        emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
        lines.append(f"## {emoji} Health Score: {score:.1f}/100")
        lines.append("")
        
        # Recommendations
        lines.append("## 💡 Recommendations")
        lines.append("")
        
        if 'missing_images' in [i['type'] for i in self.issues.get('CRITICAL', [])]:
            lines.append("1. **Upload missing images** for attachments through admin panel")
        if 'duplicate_codes' in [i['type'] for i in self.issues.get('CRITICAL', [])]:
            lines.append("2. **Fix duplicate codes** to ensure unique identification")
        if 'empty_weapons' in [i['type'] for i in self.issues.get('WARNING', [])]:
            lines.append("3. **Add attachments** to weapons that don't have any")
        if 'sparse_weapons' in [i['type'] for i in self.issues.get('WARNING', [])]:
            lines.append("4. **Enrich sparse weapons** with more attachment options")
            
        return "\n".join(lines)
        
    def run_full_check(self, save_to_db=True) -> Dict:
        """Run all health checks"""
        logger.info("🔍 Starting data health check...")
        
        # Run all checks
        self.check_missing_images()
        self.check_duplicate_codes()
        self.check_empty_weapons()
        self.check_sparse_weapons()
        self.check_orphaned_attachments()
        self.check_data_freshness()
        
        # Calculate metrics
        self.calculate_metrics()
        
        # Save to database if requested
        check_id = None
        if save_to_db:
            check_id = self.save_results()
            
        # Generate report
        text_report = self.generate_report('text')
        markdown_report = self.generate_report('markdown')
        
        # Print summary
        print(text_report)
        
        # Save markdown report to file - use /tmp for production to avoid read-only issues
        try:
            import tempfile
            report_dir = os.environ.get('HEALTH_REPORT_DIR', tempfile.gettempdir())
            report_path = os.path.join(report_dir, f'health_check_{datetime.now().strftime("%Y%m%d_%H%M%S")}.md')
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(markdown_report)
            logger.info(f"📝 Report saved to: {report_path}")
        except Exception as e:
            logger.warning(f"Could not save report to file: {e}")
            report_path = None
        
        return {
            'check_id': check_id,
            'health_score': self.calculate_health_score(),
            'critical_count': sum(i.get('count', 0) for i in self.issues.get('CRITICAL', [])),
            'warning_count': sum(i.get('count', 0) for i in self.issues.get('WARNING', [])),
            'info_count': sum(i.get('count', 0) for i in self.issues.get('INFO', [])),
            'report_path': report_path
        }


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check data health and quality")
    parser.add_argument('--auto-fix', action='store_true', help="Automatically fix simple issues (USE WITH CAUTION)")
    parser.add_argument('--no-save', action='store_true', help="Don't save results to database")
    parser.add_argument('--format', choices=['text', 'markdown'], default='text', help="Output format")
    
    args = parser.parse_args()
    
    checker = DataHealthChecker(auto_fix=args.auto_fix)
    results = checker.run_full_check(save_to_db=not args.no_save)
    
    # Exit with error code if critical issues found
    if results['critical_count'] > 0:
        sys.exit(1)
