from core.database.database_adapter import get_database_adapter
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    try:
        db = get_database_adapter()
        with open('scripts/migrations/add_attachment_soft_delete.sql', 'r', encoding='utf-8') as f:
            sql = f.read()
        
        logger.info("Executing migration...")
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        logger.info("Migration applied successfully!")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        exit(1)

if __name__ == "__main__":
    run_migration()
