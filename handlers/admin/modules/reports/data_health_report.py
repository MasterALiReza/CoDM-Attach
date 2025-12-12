"""
Data Health Report Handler - Simple Version
Admin interface for viewing and managing data health checks
بدون استفاده از ConversationHandler برای سادگی
"""

import os
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from handlers.admin.modules.base_handler import BaseAdminHandler
from handlers.admin.admin_states import ADMIN_MENU, AWAITING_BACKUP_FILE
from utils.data_health_check import DataHealthChecker
from utils.logger import get_logger
from core.security.role_manager import Permission
from utils.i18n import t
from utils.language import get_user_lang
from utils.telegram_safety import safe_edit_message_text

logger = get_logger('data_health_report', 'admin.log')

class DataHealthReportHandler(BaseAdminHandler):
    """Handler for data health reports in admin panel"""
    
    def __init__(self, db, role_manager=None):
        super().__init__(db)
        self.health_checker = DataHealthChecker(self.db)
    async def data_health_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show data health main menu"""
        query = update.callback_query
        if query:
            await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
            
        # Check permissions
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.VIEW_HEALTH_REPORTS):
            await self.send_permission_denied(update, context)
            return
            
        # Init message
        message = t('admin.health.menu.title', lang) + "\n\n"

        # Get latest health check results (safe try/with)
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Latest metrics
                cursor.execute(
                    """
                    SELECT 
                        created_at,
                        total_weapons,
                        total_attachments,
                        health_score
                    FROM data_quality_metrics
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
                latest_metrics = cursor.fetchone()

                # Active issues by severity
                cursor.execute(
                    """
                    SELECT 
                        severity,
                        COUNT(*) as count
                    FROM data_health_checks
                    GROUP BY severity
                    """
                )
                rows = cursor.fetchall()
                issue_counts = {}
                if rows:
                    for row in rows:
                        issue_counts[row.get('severity')] = row.get('count')
        except Exception as e:
            logger.error(f"Error loading data health menu: {e}")
            latest_metrics = None
            issue_counts = {}

        # Build message
        if latest_metrics:
            created_at = latest_metrics.get('created_at')
            total_weapons = latest_metrics.get('total_weapons')
            total_attachments = latest_metrics.get('total_attachments')
            health_score = latest_metrics.get('health_score')
            # Ensure numeric type for comparisons/formatting
            try:
                health_score = float(health_score)
            except (TypeError, ValueError):
                health_score = 0.0
            score_emoji = "\U0001F7E2" if health_score >= 80 else "\U0001F7E1" if health_score >= 60 else "\U0001F534"
            message += t('admin.health.menu.last_check', lang, date=str(created_at)) + "\n"
            message += t('admin.health.menu.score', lang, emoji=score_emoji, score=f"{health_score:.1f}") + "\n\n"
            message += t('admin.health.menu.stats.header', lang) + "\n"
            message += t('admin.health.menu.stats.weapons', lang, n=total_weapons) + "\n"
            message += t('admin.health.menu.stats.attachments', lang, n=total_attachments) + "\n\n"
            
            if issue_counts:
                message += t('admin.health.menu.issues.header', lang) + "\n"
                if 'CRITICAL' in issue_counts:
                    message += t('admin.health.menu.issues.critical', lang, n=issue_counts['CRITICAL']) + "\n"
                if 'WARNING' in issue_counts:
                    message += t('admin.health.menu.issues.warning', lang, n=issue_counts['WARNING']) + "\n"
                if 'INFO' in issue_counts:
                    message += t('admin.health.menu.issues.info', lang, n=issue_counts['INFO']) + "\n"
        else:
            message += t('admin.health.menu.no_report', lang) + "\n"
            
        # Build keyboard
        keyboard = []
        
        # Run check button (requires RUN_HEALTH_CHECKS permission)
        can_run = await self.check_permission(user_id, Permission.RUN_HEALTH_CHECKS)
        if can_run:
            keyboard.append([
                InlineKeyboardButton(t('admin.health.buttons.run_check', lang), callback_data="run_health_check")
            ])
            
        # View reports buttons
        keyboard.extend([
            [
                InlineKeyboardButton(t('admin.health.buttons.view_full', lang), callback_data="view_full_report"),
                InlineKeyboardButton(t('admin.health.buttons.critical', lang), callback_data="view_critical")
            ],
            [
                InlineKeyboardButton(t('admin.health.buttons.warnings', lang), callback_data="view_warnings"),
                InlineKeyboardButton(t('admin.health.buttons.detailed', lang), callback_data="view_detailed_stats")
            ]
        ])
        
        # Fix issues button (requires FIX_DATA_ISSUES permission)
        can_fix = await self.check_permission(user_id, Permission.FIX_DATA_ISSUES)
        if can_fix:
            keyboard.append([
                InlineKeyboardButton(t('admin.health.buttons.fix_issues', lang), callback_data="fix_issues_menu")
            ])
            
        # History and back buttons
        keyboard.extend([
            [InlineKeyboardButton(t('admin.health.buttons.history', lang), callback_data="view_check_history")],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="admin_menu_return")]
        ])
        
        if query:
            await safe_edit_message_text(
                query,
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_message(
                update.effective_chat.id,
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        # No return needed for simple handler
        
    async def run_health_check(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Run a new health check"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.health.run.start', lang))
        
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.RUN_HEALTH_CHECKS):
            await self.send_permission_denied(update, context)
            return
            
        # Show progress message
        await safe_edit_message_text(
            query,
            t('admin.health.run.progress', lang),
            parse_mode=ParseMode.MARKDOWN
        )
        
        try:
            # Run health check
            results = self.health_checker.run_full_check(save_to_db=True)
            
            # Build result message
            score = results['health_score']
            score_emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
            
            message = t('admin.health.run.completed.title', lang) + "\n\n"
            message += t('admin.health.run.completed.score', lang, emoji=score_emoji, score=f"{score:.1f}") + "\n\n"
            if results['critical_count'] > 0:
                message += t('admin.health.run.completed.critical', lang, n=results['critical_count']) + "\n"
            if results['warning_count'] > 0:
                message += t('admin.health.run.completed.warnings', lang, n=results['warning_count']) + "\n"
            if results['info_count'] > 0:
                message += t('admin.health.run.completed.info', lang, n=results['info_count']) + "\n"
            message += "\n" + t('admin.health.run.completed.saved', lang, file=os.path.basename(results['report_path']))
            
            # Send report file
            if os.path.exists(results['report_path']):
                with open(results['report_path'], 'rb') as f:
                    await context.bot.send_document(
                        chat_id=update.effective_chat.id,
                        document=f,
                        filename=os.path.basename(results['report_path']),
                        caption=t('admin.health.run.report_caption', lang)
                    )
                    
        except Exception as e:
            message = t('admin.health.run.error', lang, err=str(e))
            logger.error(f"Health check error: {e}")
            
        # Update message with back button
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="data_health")]]
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # No return needed for simple handler
        
    async def view_critical(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """View critical issues"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    check_type,
                    issue_count,
                    details,
                    created_at
                FROM data_health_checks
                WHERE severity = 'CRITICAL'
                ORDER BY created_at DESC
                LIMIT 10
                """)
                
                critical_issues = cursor.fetchall()
        except Exception as e:
            logger.error(f"Error loading critical issues: {e}")
            critical_issues = []
            
        message = t('admin.health.critical.title', lang) + "\n\n"
        
        if critical_issues:
            for issue in critical_issues:
                check_type = issue.get('check_type')
                count = issue.get('issue_count')
                details_json = issue.get('details')
                created_at = issue.get('created_at')
                details = json.loads(details_json) if isinstance(details_json, str) and details_json else {}
                
                if check_type == 'missing_images':
                    message += f"🖼️ **{t('admin.health.type.missing_images', lang)}:** {count} {t('admin.health.issue.unit', lang)}\n"
                elif check_type == 'duplicate_codes':
                    message += f"🔁 **{t('admin.health.type.duplicate_codes', lang)}:** {count} {t('admin.health.issue.unit', lang)}\n"
                elif check_type == 'orphaned_attachments':
                    message += f"🧩 **{t('admin.health.type.orphaned_attachments', lang)}:** {count} {t('admin.health.issue.unit', lang)}\n"
                
                date_str = created_at.strftime('%Y-%m-%d') if hasattr(created_at, 'strftime') else (str(created_at)[:10] if created_at else '-')
                message += t('admin.health.date', lang, date=date_str) + "\n\n"
        else:
            message += t('admin.health.critical.none', lang)
            
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="data_health")]]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # No return needed for simple handler
        
    async def view_warnings(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """View warning issues"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    check_type,
                    issue_count,
                    details,
                    created_at
                FROM data_health_checks
                WHERE severity = 'WARNING'
                ORDER BY created_at DESC
                LIMIT 10
                """)
                
                warnings = cursor.fetchall()
            
        except Exception as e:
            logger.error(f"Error loading warnings: {e}")
            warnings = []
            
        message = t('admin.health.warnings.title', lang) + "\n\n"
        
        if warnings:
            for warning in warnings:
                check_type = warning.get('check_type')
                count = warning.get('issue_count')
                details_json = warning.get('details')
                created_at = warning.get('created_at')
                
                if check_type == 'empty_weapons':
                    message += f"🗡️ **{t('admin.health.type.empty_weapons', lang)}:** {count} {t('admin.health.issue.unit', lang)}\n"
                elif check_type == 'sparse_weapons':
                    message += f"🟨 **{t('admin.health.type.sparse_weapons', lang)}:** {count} {t('admin.health.issue.unit', lang)}\n"
                
                date_str = created_at.strftime('%Y-%m-%d') if hasattr(created_at, 'strftime') else (str(created_at)[:10] if created_at else '-')
                message += t('admin.health.date', lang, date=date_str) + "\n\n"
        else:
            message += t('admin.health.warnings.none', lang)
            
        keyboard = [
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="data_health")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # No return needed for simple handler
        
    async def view_full_report(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """View full report with all issues"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Get latest metrics
                cursor.execute("""
                SELECT 
                    created_at,
                    health_score,
                    total_weapons,
                    total_attachments,
                    attachments_with_images,
                    attachments_without_images
                FROM data_quality_metrics
                ORDER BY created_at DESC
                LIMIT 1
                """)
                latest = cursor.fetchone()
                
                # Get all issues
                cursor.execute("""
                SELECT 
                    severity,
                    check_type,
                    issue_count
                FROM data_health_checks
                ORDER BY 
                    CASE severity 
                        WHEN 'CRITICAL' THEN 1
                        WHEN 'WARNING' THEN 2
                        ELSE 3
                    END,
                    created_at DESC
                """)
                issues = cursor.fetchall()
        except Exception as e:
            logger.error(f"Error loading full report: {e}")
            latest = None
            issues = []
            
        message = t('admin.health.full.title', lang) + "\n\n"
        
        if latest:
            date = latest.get('created_at')
            score = latest.get('health_score')
            weapons = latest.get('total_weapons')
            attachments = latest.get('total_attachments')
            with_img = latest.get('attachments_with_images')
            without_img = latest.get('attachments_without_images')
            # Ensure numeric type for comparisons/formatting
            try:
                score = float(score)
            except (TypeError, ValueError):
                score = 0.0
            score_emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
            
            date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else (str(date)[:10] if date else '-')
            message += t('admin.health.date', lang, date=date_str) + "\n"
            message += t('admin.health.run.completed.score', lang, emoji=score_emoji, score=f"{score:.1f}") + "\n\n"
            
            message += t('admin.health.menu.stats.header', lang) + "\n"
            message += t('admin.health.menu.stats.weapons', lang, n=weapons) + "\n"
            message += t('admin.health.menu.stats.attachments', lang, n=attachments) + "\n"
            message += t('admin.health.stats.with_images', lang, n=with_img) + "\n"
            message += t('admin.health.stats.without_images', lang, n=without_img) + "\n\n"
            
            if issues:
                message += t('admin.health.open_issues.header', lang) + "\n"
                for row in issues:
                    severity = row.get('severity')
                    check_type = row.get('check_type')
                    count = row.get('issue_count')
                    emoji = "❌" if severity == "CRITICAL" else "⚠️" if severity == "WARNING" else "ℹ️"
                    type_title = {
                        'missing_images': t('admin.health.type.missing_images', lang),
                        'duplicate_codes': t('admin.health.type.duplicate_codes', lang),
                        'empty_weapons': t('admin.health.type.empty_weapons', lang),
                        'sparse_weapons': t('admin.health.type.sparse_weapons', lang),
                        'orphaned_attachments': t('admin.health.type.orphaned_attachments', lang)
                    }.get(check_type, check_type)
                    message += f"{emoji} {type_title}: {count} {t('admin.health.issue.unit', lang)}\n"
            else:
                message += t('admin.health.full.no_issues', lang)
        else:
            message += t('admin.health.full.no_checks', lang)
            
        keyboard = [
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="data_health")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # No return needed for simple handler
        
    async def view_detailed_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """View detailed statistics"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # Calculate fresh metrics
        self.health_checker.calculate_metrics()
        metrics = self.health_checker.metrics
        
        message = t('admin.health.detailed.title', lang) + "\n\n"
        message += t('admin.health.detailed.total.header', lang) + "\n"
        message += t('admin.health.detailed.total.categories', lang, n=metrics.get('total_categories', 0)) + "\n"
        message += t('admin.health.menu.stats.weapons', lang, n=metrics.get('total_weapons', 0)) + "\n"
        message += t('admin.health.menu.stats.attachments', lang, n=metrics.get('total_attachments', 0)) + "\n\n"
        
        message += t('admin.health.detailed.special.header', lang) + "\n"
        message += t('admin.health.detailed.special.top', lang, n=metrics.get('top_attachments', 0)) + "\n"
        message += t('admin.health.detailed.special.season', lang, n=metrics.get('season_attachments', 0)) + "\n\n"
        
        message += t('admin.health.detailed.images.header', lang) + "\n"
        message += t('admin.health.detailed.images.line', lang, pct=f"{metrics.get('image_coverage', 0):.1f}") + "\n\n"
        
        if metrics.get('category_distribution'):
            message += t('admin.health.detailed.catdist.header', lang) + "\n"
            for cat in metrics['category_distribution']:
                # Escape markdown characters in category name
                safe_category = cat['category'].replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
                message += t('admin.health.detailed.catdist.line', lang, category=safe_category, weapons=cat['weapons'], attachments=cat['attachments']) + "\n"
                
        keyboard = [
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="data_health")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # No return needed for simple handler
        
    async def view_check_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """View history of health checks"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    created_at,
                    health_score,
                    total_weapons,
                    total_attachments,
                    attachments_with_images,
                    attachments_without_images
                FROM data_quality_metrics
                ORDER BY created_at DESC
                LIMIT 10
            """)
                
                history = cursor.fetchall()
        finally:
            pass  # Connection auto-closed by context manager
            
        message = t('admin.health.history.title', lang) + "\n\n"
        
        if history:
            for record in history:
                date = record.get('created_at')
                score = record.get('health_score')
                weapons = record.get('total_weapons')
                attachments = record.get('total_attachments')
                with_img = record.get('attachments_with_images')
                without_img = record.get('attachments_without_images')
                # Ensure numeric type for comparisons/formatting
                try:
                    score = float(score)
                except (TypeError, ValueError):
                    score = 0.0
                score_emoji = "🟢" if score >= 80 else "🟡" if score >= 60 else "🔴"
                
                date_str = date.strftime('%Y-%m-%d') if hasattr(date, 'strftime') else (str(date)[:10] if date else '-')
                message += f"📅 **{date_str}**\n"
                message += f"{score_emoji} {t('admin.health.run.completed.score', lang, emoji=score_emoji, score=f'{score:.1f}')}\n"
                message += f"• {t('admin.health.menu.stats.weapons', lang, n=weapons)} | {t('admin.health.menu.stats.attachments', lang, n=attachments)}\n"
                message += f"• {t('admin.health.stats.with_images', lang, n=with_img)} | {t('admin.health.stats.without_images', lang, n=without_img)}\n\n"
        else:
            message += t('admin.health.history.none', lang)
            
        keyboard = [
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="data_health")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # No return needed for simple handler
        
    async def fix_issues_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show menu for fixing issues"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.FIX_DATA_ISSUES):
            await self.send_permission_denied(update, context)
            return
            
        message = t('admin.health.fix.menu.title', lang) + "\n\n" + t('admin.health.fix.menu.note', lang) + "\n\n" + t('admin.health.fix.menu.prompt', lang)
        
        keyboard = [
            [InlineKeyboardButton(t('admin.health.fix.buttons.missing_images', lang), callback_data="fix_missing_images")],
            [InlineKeyboardButton(t('admin.health.fix.buttons.duplicate_codes', lang), callback_data="fix_duplicate_codes")],
            [InlineKeyboardButton(t('admin.health.fix.buttons.orphaned', lang), callback_data="fix_orphaned")],
            [
                InlineKeyboardButton(t('admin.health.fix.buttons.create_backup', lang), callback_data="create_backup"),
                InlineKeyboardButton(t('admin.health.fix.buttons.restore_backup', lang), callback_data="restore_backup")
            ],
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="data_health")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # No return needed
        
    async def fix_missing_images(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show list of attachments without images"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.health.loading.missing_images', lang))
        
        # Check permission
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.FIX_DATA_ISSUES):
            await self.send_permission_denied(update, context)
            return
        
        # Get all attachments without images
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    a.id,
                    a.name,
                    a.code,
                    wc.name as category,
                    w.name as weapon,
                    a.mode
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                JOIN weapon_categories wc ON w.category_id = wc.id
                WHERE a.image_file_id IS NULL OR a.image_file_id = ''
                ORDER BY wc.name, w.name
                LIMIT 20
            """)
                
                missing_images = cursor.fetchall()
                total = len(missing_images)
        finally:
            pass  # Connection auto-closed by context manager
            
        message = t('admin.health.missing_images.title', lang) + "\n\n"
        
        if missing_images:
            message += t('admin.health.list.total', lang, n=total) + "\n"
            message += t('admin.health.list.showing', lang, n=min(20, total)) + "\n\n"
            
            current_category = None
            for row in missing_images:
                att_id = row.get('id')
                name = row.get('name')
                code = row.get('code')
                category = row.get('category')
                weapon = row.get('weapon')
                mode = row.get('mode')
                if category != current_category:
                    current_category = category
                    message += f"\n**{category}:**\n"
                    
                mode_emoji = "🪂" if mode == "br" else "🎮"
                message += f"{mode_emoji} {weapon} - {name} (`{code}`)\n"
                
            message += "\n" + t('admin.health.missing_images.hint.title', lang) + "\n"
            message += t('admin.health.missing_images.hint.edit', lang) + "\n"
            message += t('admin.health.missing_images.hint.check', lang) + "\n"
            message += t('admin.health.missing_images.hint.quality', lang) + "\n"
        else:
            message += t('admin.health.missing_images.none', lang)
        
        keyboard = [
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fix_issues_menu")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    async def fix_duplicate_codes(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show and fix duplicate attachment codes"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.health.loading.duplicates', lang))
        
        # Check permission
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.FIX_DATA_ISSUES):
            await self.send_permission_denied(update, context)
            return
        
        # Find duplicate codes
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT 
                    LOWER(a.code) as code,
                    COUNT(*) as count,
                    STRING_AGG(a.name || ' (' || w.name || ')', ', ') as attachments
                FROM attachments a
                JOIN weapons w ON a.weapon_id = w.id
                GROUP BY LOWER(a.code)
                HAVING COUNT(*) > 1
                ORDER BY count DESC
                LIMIT 10
            """)
                
                duplicates = cursor.fetchall()
        finally:
            pass  # Connection auto-closed by context manager
            
        message = t('admin.health.duplicates.title', lang) + "\n\n"
        
        if duplicates:
            message += t('admin.health.list.total', lang, n=len(duplicates)) + "\n\n"
            
            for row in duplicates:
                code = row.get('code')
                count = row.get('count')
                attachments = row.get('attachments')

                message += f"• `{code}` - {count} {t('admin.health.issue.unit', lang)}\n"
                att_list = attachments.split(',')
                for att in att_list[:3]:  # نمایش 3 مورد اول
                    message += f"  • {att.strip()}\n"
                if len(att_list) > 3:
                    message += f"  • {t('common.items_other_count', lang, n=len(att_list) - 3)}\n"
                message += "\n"
                
            message += t('admin.health.duplicates.note', lang) + "\n\n"
            message += t('admin.health.duplicates.hint.title', lang) + "\n"
            message += t('admin.health.duplicates.hint.fix', lang) + "\n"
            message += t('admin.health.duplicates.hint.remove', lang) + "\n"
        else:
            message += t('admin.health.duplicates.none', lang)
            
        keyboard = [
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fix_issues_menu")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    async def fix_orphaned(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Find and optionally remove orphaned attachments"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.health.loading.orphaned', lang))
        
        # Check permission
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.FIX_DATA_ISSUES):
            await self.send_permission_denied(update, context)
            return
        
        # Find orphaned attachments (attachments with deleted weapon_id)
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                # Find attachments with non-existent weapon_id
                cursor.execute("""
                SELECT 
                    a.id,
                    a.name,
                    a.code,
                    a.weapon_id
                FROM attachments a
                LEFT JOIN weapons w ON a.weapon_id = w.id
                WHERE w.id IS NULL
                LIMIT 20
            """)
                
                orphaned = cursor.fetchall()
        finally:
            pass  # Connection auto-closed by context manager
            
        message = t('admin.health.orphaned.title', lang) + "\n\n"
        message += t('admin.health.orphaned.desc', lang) + "\n\n"
        
        if orphaned:
            message += t('admin.health.list.total', lang, n=len(orphaned)) + "\n\n"
            
            for row in orphaned:
                att_id = row.get('id')
                name = row.get('name')
                code = row.get('code')
                weapon_id = row.get('weapon_id')
                message += f"• {name} (`{code}`)\n"
                message += t('admin.health.orphaned.weapon_id', lang, id=weapon_id) + "\n\n"
                
            message += t('admin.health.orphaned.note', lang) + "\n\n"
            
            message += t('admin.health.orphaned.hint.title', lang) + "\n"
            message += t('admin.health.orphaned.hint.restore', lang) + "\n"
            message += t('admin.health.orphaned.hint.cleanup', lang) + "\n"
        else:
            message += t('admin.health.orphaned.none', lang)
        
        keyboard = [
            [InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fix_issues_menu")]
        ]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    async def create_backup(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Create database backup and send to admin"""
        query = update.callback_query
        lang = get_user_lang(update, context, self.db) or 'fa'
        await query.answer(t('admin.health.backup.start', lang))
        
        # Check permission
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.FIX_DATA_ISSUES):
            await self.send_permission_denied(update, context)
            return
        
        # PostgreSQL: in-app backup unsupported, show hint
        if hasattr(self.db, 'is_postgres') and self.db.is_postgres():
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fix_issues_menu")]]
            await safe_edit_message_text(
                query,
                t('admin.health.backup.pg_unsupported', lang),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        try:
            from datetime import datetime
            import shutil
            
            db_path = self.health_checker.db_path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"codm_backup_{timestamp}.db"
            backup_path = os.path.join(os.path.dirname(db_path), backup_filename)
            
            # Create backup
            shutil.copy2(db_path, backup_path)
            
            # Get file size
            file_size = os.path.getsize(backup_path)
            size_mb = file_size / (1024 * 1024)
            
            # Send backup file to admin
            with open(backup_path, 'rb') as backup_file:
                caption = t('admin.health.backup.caption.title', lang) + "\n\n"
                caption += t('admin.health.backup.caption.date', lang, date=timestamp[:8]) + "\n"
                caption += t('admin.health.backup.caption.time', lang, time=timestamp[9:]) + "\n"
                caption += t('admin.health.backup.caption.size', lang, size=f"{size_mb:.2f}") + "\n\n"
                caption += t('admin.health.backup.caption.note', lang)
                
                await context.bot.send_document(
                    chat_id=update.effective_chat.id,
                    document=backup_file,
                    filename=backup_filename,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN
                )
            
            message = t('admin.health.backup.success.title', lang) + "\n\n"
            message += t('admin.health.backup.success.sent', lang) + "\n"
            message += t('admin.health.backup.caption.size', lang, size=f"{size_mb:.2f}") + "\n\n"
            message += t('admin.health.backup.success.tip_restore', lang)
            
        except Exception as e:
            message = t('admin.health.backup.error', lang, err=str(e))
            logger.error(f"Backup error: {e}")
            
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fix_issues_menu")]]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    async def restore_backup_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Start backup restoration process"""
        query = update.callback_query
        await query.answer()
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # Check permission
        user_id = update.effective_user.id
        if not await self.check_permission(user_id, Permission.FIX_DATA_ISSUES):
            await self.send_permission_denied(update, context)
            return ADMIN_MENU
        
        message = (
            t('admin.health.restore.start.title', lang) + "\n\n" +
            t('admin.health.restore.start.steps_header', lang) + "\n" +
            t('admin.health.restore.start.step1', lang) + "\n" +
            t('admin.health.restore.start.step2', lang) + "\n\n" +
            t('admin.health.restore.start.prompt', lang) + "\n" +
            t('admin.health.restore.start.cancel', lang)
        )
        
        keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fix_issues_menu")]]
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        return AWAITING_BACKUP_FILE
        
    async def restore_backup_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Handle received backup file and restore it"""
        user_id = update.effective_user.id
        lang = get_user_lang(update, context, self.db) or 'fa'
        
        # Check permission
        if not await self.check_permission(user_id, Permission.FIX_DATA_ISSUES):
            await self.send_permission_denied(update, context)
            return ADMIN_MENU
        
        # Check if document exists
        if not update.message.document:
            await update.message.reply_text(
                t('admin.health.restore.file_required', lang) + "\n" + t('admin.health.restore.start.cancel', lang)
            )
            return AWAITING_BACKUP_FILE
        
        document = update.message.document
        
        # Check file extension
        if not document.file_name.endswith('.db'):
            await update.message.reply_text(
                t('admin.health.restore.invalid_format', lang) + "\n" + t('admin.health.restore.start.cancel', lang)
            )
            return AWAITING_BACKUP_FILE
        
        try:
            import shutil
            from datetime import datetime
            
            # Download file
            file = await context.bot.get_file(document.file_id)
            temp_path = f"temp_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            await file.download_to_drive(temp_path)
            
            # Create safety backup first
            db_path = self.health_checker.db_path
            safety_backup = f"{db_path}.before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            shutil.copy2(db_path, safety_backup)
            
            # Restore backup
            shutil.copy2(temp_path, db_path)
            
            # Clean up temp file
            os.remove(temp_path)
            
            message = t('admin.health.restore.success.title', lang) + "\n\n"
            message += t('admin.health.restore.success.safety_backup', lang, file=os.path.basename(safety_backup)) + "\n\n"
            message += t('admin.health.restore.success.restart', lang, cmd="python main.py")
            
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fix_issues_menu")]]
            
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"Database restored by admin {user_id}")
            
        except Exception as e:
            message = t('admin.health.restore.error', lang, err=str(e))
            
            keyboard = [[InlineKeyboardButton(t('menu.buttons.back', lang), callback_data="fix_issues_menu")]]
            
            await update.message.reply_text(
                message,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            logger.error(f"Restore error: {e}")
        
        return ADMIN_MENU


