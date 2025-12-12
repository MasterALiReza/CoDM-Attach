
import logging
from datetime import timedelta, time
from telegram.ext import Application, ContextTypes

# Assuming BackupManager is available to be imported
from managers.backup_manager import BackupManager

logger = logging.getLogger(__name__)

class BackupScheduler:
    """
    Manages automated backup scheduling using Telegram's JobQueue.
    """
    
    def __init__(self, db_adapter):
        self.db = db_adapter
        self.backup_manager = BackupManager(db_adapter)
        self.job_name = "auto_backup_job"

    async def start(self, application: Application):
        """
        Initializes the scheduler by reading settings from DB and scheduling the job if enabled.
        Should be called during bot startup (post_init).
        """
        try:
            # Load settings
            enabled = self.db.get_setting("auto_backup_enabled", "0") == "1"
            interval = self.db.get_setting("auto_backup_interval", "24h")
            
            if enabled:
                await self.schedule_job(application, interval)
                logger.info(f"Auto-backup scheduler started with interval: {interval}")
            else:
                logger.info("Auto-backup is disabled in settings.")
                
        except Exception as e:
            logger.error(f"Failed to start backup scheduler: {e}")

    async def schedule_job(self, application: Application, interval_str: str):
        """
        Schedules the backup job with the specified interval.
        Removes existing job if present.
        """
        job_queue = application.job_queue
        if not job_queue:
            logger.error("JobQueue is not available in application!")
            return

        # Remove existing job
        current_jobs = job_queue.get_jobs_by_name(self.job_name)
        for job in current_jobs:
            job.schedule_removal()

        # Parse interval
        interval_seconds = self._parse_interval(interval_str)
        
        # Schedule message
        # We use run_repeating. first=10 means start 10 seconds after bot launch (or immediate if running)
        # to ensure we don't block startup, but also don't wait a full cycle for the first run?
        # Actually standard practice is usually wait a bit or wait full interval. 
        # For backups, let's wait the interval to avoid spamming on restarts, OR maybe a fixed time.
        # "24h" implies daily. Ideally users might want to set a TIME. 
        # But for now, simple interval is fine.
        
        job_queue.run_repeating(
            self.execute_backup_job,
            interval=interval_seconds,
            first=interval_seconds, # Don't run immediately on startup, wait for first interval
            name=self.job_name
        )
        logger.info(f"Scheduled auto-backup job every {interval_seconds} seconds")

    async def stop(self, application: Application):
        """Stops the backup job."""
        job_queue = application.job_queue
        if job_queue:
            current_jobs = job_queue.get_jobs_by_name(self.job_name)
            for job in current_jobs:
                job.schedule_removal()
        logger.info("Auto-backup job stopped.")

    async def update_schedule(self, application: Application, enabled: bool, interval_str: str):
        """
        Updates the schedule based on new settings (called from Admin UI).
        """
        # Save to DB
        self.db.set_setting("auto_backup_enabled", "1" if enabled else "0")
        self.db.set_setting("auto_backup_interval", interval_str)
        
        if enabled:
            await self.schedule_job(application, interval_str)
        else:
            await self.stop(application)

    async def execute_backup_job(self, context: ContextTypes.DEFAULT_TYPE):
        """
        Callback function that executes the actual backup.
        """
        logger.info("⏳ Starting automated backup job...")
        try:
            # Perform backup
            backup_file = self.backup_manager.create_full_backup()
            
            if backup_file:
                logger.info(f"✅ Auto-backup completed: {backup_file}")
                
                # Cleanup old backups (keep last 10 by default)
                self.backup_manager.cleanup_old_backups(keep_count=10)
                
                # Update last backup timestamp in DB (optional, mainly for UI)
                from datetime import datetime
                self.db.set_setting("last_backup_timestamp", datetime.now().strftime("%Y-%m-%d %H:%M"))
                
                # Optional: Notify admins? (Maybe too noisy, leaving out for now unless requested)
            else:
                logger.error("❌ Auto-backup failed to create file.")
                
        except Exception as e:
            logger.error(f"❌ Error during auto-backup job: {e}")

    def _parse_interval(self, interval_str: str) -> float:
        """Converts interval string to seconds."""
        if interval_str == "24h":
            return timedelta(hours=24).total_seconds()
        elif interval_str == "1w":
            return timedelta(weeks=1).total_seconds()
        elif interval_str == "2w":
            return timedelta(weeks=2).total_seconds()
        elif interval_str == "1m":
            return timedelta(days=30).total_seconds() # Approx
        else:
            # Default to 24h if unknown
            return timedelta(hours=24).total_seconds()
