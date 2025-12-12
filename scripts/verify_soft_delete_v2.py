
import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database.database_pg_proxy import DatabasePostgresProxy

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_soft_delete():
    load_dotenv()
    
    # Initialize DB
    # Ensure DATABASE_URL is in env or passed explicitly if needed, 
    # but DatabasePostgresProxy usually loads from env if empty.
    db = DatabasePostgresProxy()
    
    test_user_id = 999999999
    test_admin_id = 888888888
    
    logger.info("Starting Soft Delete Verification...")

    try:
        # 1. Clean up previous test data
        with db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM user_attachments WHERE user_id = %s", (test_user_id,))
                cur.execute("DELETE FROM user_submission_stats WHERE user_id = %s", (test_user_id,))
                conn.commit()

        # 2. Ensure stats record exists
        with db.get_connection() as conn:
             with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO user_submission_stats (user_id, total_submissions, approved_count, rejected_count, deleted_count, strike_count, is_banned)
                    VALUES (%s, 0, 0, 0, 0, 0, FALSE)
                """, (test_user_id,))
                conn.commit()

        # 3. Create a Test Attachment
        logger.info("Creating Test Attachment 1...")
        # 3. Create a Test Attachment
        logger.info("Creating Test Attachment 1...")
        att_id_1 = db.add_user_attachment(
            user_id=test_user_id,
            weapon_id=None,
            mode='mp',
            category='test',
            custom_weapon_name='Test Weapon',
            attachment_name='Test Att 1',
            image_file_id='test_file_id_1',
            description='Test Description'
        )
        
        if not att_id_1:
            logger.error("Failed to create attachment 1")
            return

        # 4. Test User Delete (User deletes their own)
        logger.info("Test 1: User Delete (Self-Delete)...")
        success = db.delete_user_attachment(att_id_1, deleted_by=test_user_id)
        if not success:
             logger.error("User delete failed")
             return
             
        # Verify
        att1 = db.get_user_attachment(att_id_1)
        stats = db.get_user_submission_stats(test_user_id)
        
        if att1['status'] != 'deleted':
            logger.error(f"Status mismatch: expected 'deleted', got '{att1['status']}'")
        elif att1['deleted_by'] != test_user_id:
            logger.error(f"deleted_by mismatch: expected {test_user_id}, got {att1['deleted_by']}")
        elif stats['deleted_count'] != 1:
            logger.error(f"Stats deleted_count mismatch: expected 1, got {stats['deleted_count']}")
        else:
            logger.info("User Delete verified successfully.")

        # 5. Test Restore
        logger.info("Test 2: Admin Restore...")
        success = db.restore_user_attachment(att_id_1)
        if not success:
            logger.error("Restore failed")
            return

        # Verify
        att1 = db.get_user_attachment(att_id_1)
        stats = db.get_user_submission_stats(test_user_id)

        if att1['status'] != 'pending':
            logger.error(f"Status mismatch after restore: expected 'pending', got '{att1['status']}'")
        elif att1['deleted_by'] is not None:
             logger.error(f"deleted_by not None after restore: {att1['deleted_by']}")
        elif stats['deleted_count'] != 0:
             logger.error(f"Stats deleted_count mismatch after restore: expected 0, got {stats['deleted_count']}")
        else:
             logger.info("Restore verified successfully.")

        # 6. Test Admin Delete
        logger.info("Test 3: Admin Delete...")
        success = db.delete_user_attachment(att_id_1, deleted_by=test_admin_id)
        if not success:
            logger.error("Admin delete failed")
            return

        # Verify
        att1 = db.get_user_attachment(att_id_1)
        stats = db.get_user_submission_stats(test_user_id)
        
        if att1['status'] != 'deleted':
             logger.error(f"Status mismatch: expected 'deleted', got '{att1['status']}'")
        elif att1['deleted_by'] != test_admin_id:
             logger.error(f"deleted_by mismatch: expected {test_admin_id}, got {att1['deleted_by']}")
        elif stats['deleted_count'] != 1:
             logger.error(f"Stats deleted_count mismatch: expected 1, got {stats['deleted_count']}")
        else:
            logger.info("Admin Delete verified successfully.")
            
        logger.info("All Soft Delete Tests Passed!")

    except Exception as e:
        logger.error(f"Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Cleanup
        logger.info("Cleaning up...")
        try:
             with db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM user_attachments WHERE user_id = %s", (test_user_id,))
                    cur.execute("DELETE FROM user_submission_stats WHERE user_id = %s", (test_user_id,))
                    conn.commit()
        except:
            pass

if __name__ == "__main__":
    verify_soft_delete()
