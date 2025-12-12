import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from core.database.database_pg_proxy import DatabasePostgresProxy

async def seed_faqs():
    print("Connecting to database...")
    db = DatabasePostgresProxy()
    
    # Default FAQs - 5 for FA, 5 for EN
    # Signature: add_faq(question, answer, category, lang)
    defaults = [
        # FA
        {
            "question": "چگونه از ربات استفاده کنم؟",
            "answer": "از منوی اصلی، **مود بازی** (بتل رویال یا مولتی پلیر) را انتخاب کنید. سپس نوع تفنگ (مثلاً Assault) و خود تفنگ را انتخاب کنید تا بهترین اتچمنت‌ها برای شما نمایش داده شود.",
            "category": "general",
            "lang": "fa"
        },
        {
            "question": "چگونه اتچمنت خود را ثبت کنم؟",
            "answer": "از منوی اصلی وارد بخش **🎮 اتچمنت کاربران** شوید و دکمه **📤 ارسال اتچمنت** را بزنید. سپس طبق راهنما، نام، عکس و کد اتچمنت خود را بفرستید تا پس از تایید در ربات قرار گیرد.",
            "category": "user_content",
            "lang": "fa"
        },
        {
            "question": "چرا اتچمنت من هنوز تایید نشده؟",
            "answer": "همه اتچمنت‌های ارسالی کاربران باید توسط **ادمین‌ها** بررسی شوند تا از کیفیت آن‌ها اطمینان حاصل شود. این فرآیند ممکن است کمی زمان ببرد. پس از بررسی، نتیجه به شما اطلاع داده می‌شود.",
            "category": "user_content",
            "lang": "fa"
        },
        {
            "question": "چگونه با پشتیبانی تماس بگیرم؟",
            "answer": "از منوی اصلی دکمه **📞 تماس با ما** را انتخاب کنید. می‌توانید **تیکت** ثبت کنید، پیام مستقیم بفرستید یا پیشنهاد/انتقاد خود را مطرح کنید.",
            "category": "support",
            "lang": "fa"
        },
        {
            "question": "سلاح‌های متا کدامند؟",
            "answer": "در بخش انتخاب سلاح، تفنگ‌هایی که با علامت 🔥 مشخص شده‌اند، معمولاً جزو متای سیزن جاری هستند و قدرت بالایی دارند.",
            "category": "gameplay",
            "lang": "fa"
        },
        # EN
        {
            "question": "How do I use the bot?",
            "answer": "Select your **Game Mode** (Battle Royale or Multiplayer) from the main menu. Then choose a weapon category and the specific weapon to see the best recommended attachments/gunsmiths.",
            "category": "general",
            "lang": "en"
        },
        {
            "question": "How can I submit my own loadout?",
            "answer": "Go to **🎮 User Attachments** in the main menu and click **📤 Submit Attachment**. Follow the prompts to send your loadout name, screenshot, and code.",
            "category": "user_content",
            "lang": "en"
        },
        {
            "question": "Why is my submission pending?",
            "answer": "All user submissions are reviewed by **admins** manually to ensure quality. This process takes some time. You will receive a notification once your loadout is approved or rejected.",
            "category": "user_content",
            "lang": "en"
        },
        {
            "question": "How to contact support?",
            "answer": "Select **📞 Contact Us** from the main menu. You can open a **Ticket**, send a direct message, or leave feedback.",
            "category": "support",
            "lang": "en"
        },
        {
            "question": "Which weapons are META?",
            "answer": "In the weapon selection menu, weapons marked with a 🔥 icon are usually considered the current season's META (Most Effective Tactics Available).",
            "category": "gameplay",
            "lang": "en"
        }
    ]
    
    count = 0
    print(f"Attempting to seed {len(defaults)} FAQs...")
    
    # Check schema first using direct query to ensure exception is raised if column missing
    try:
        # Probe for 'lang' column
        db.execute_query("SELECT lang FROM faqs LIMIT 1;")
    except Exception as e:
        error_str = str(e)
        # Check for specific postgres error or just assume if it failed it might be the column if text matches
        if "UndefinedColumn" in error_str or "column \"lang\"" in error_str or "does not exist" in error_str:
            print("(!) Schema mismatch detected (missing 'lang' column).")
            print("(!) Attempting to DROP and RECREATE 'faqs' table...")
            try:
                # DROP
                db.execute_query("DROP TABLE IF EXISTS faqs CASCADE;")
                print("Table dropped.")
                
                # CREATE
                create_sql = """
                CREATE TABLE IF NOT EXISTS faqs (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    category VARCHAR(50) DEFAULT 'general',
                    views INTEGER DEFAULT 0,
                    helpful_count INTEGER NOT NULL DEFAULT 0,
                    not_helpful_count INTEGER NOT NULL DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    lang VARCHAR(8) NOT NULL DEFAULT 'fa',
                    UNIQUE(question, lang)
                );
                
                CREATE INDEX IF NOT EXISTS idx_faqs_category ON faqs (category) WHERE is_active = TRUE;
                CREATE INDEX IF NOT EXISTS idx_faqs_language ON faqs (language); -- Note: language or lang? SQL uses 'lang', but idx uses 'language'?
                -- Wait, setup_database.sql had 'language' column in one version and 'lang' in another?
                -- Let's check setup_database.sql content again.
                -- It had "language TEXT DEFAULT 'fa'".
                -- BUT DatabasePostgresProxy add_faq uses 'lang'.
                -- This is a mismatch in the project code!!
                -- database_pg_proxy.py line 3568: INSERT INTO faqs (..., lang)
                -- setup_database.sql line 257: language TEXT DEFAULT 'fa'
                -- This is the root cause!!! The python code expects 'lang' but table has 'language' (or vice versa).
                -- Proxy uses 'lang'. Setup uses 'language'.
                
                -- We must align them. Since we are recreating the table, we should use 'lang' to match the proxy code.
                -- OR change proxy code to use 'language'. Changing proxy is better if 'language' is more descriptive, 
                -- but changing table is easier here since we are dropping it.
                -- Let's stick to 'lang' as per proxy expectation OR rename column in CREATE.
                
                -- Actually, let's look at the failed query in log: "column "lang" of relation "faqs" does not exist".
                -- It means table has 'language' (from setup_database.sql) but code uses 'lang'.
                -- I will Create table with 'lang' column to match Python code.
                """
                
                # We need to be careful. The setup_database.sql uses 'language'. 
                # If I change it to 'lang' here, it fixes the python code, but future setups might use 'language'.
                # Use 'lang' to match the code I saw in add_faq.
                
                create_sql_fixed = """
                CREATE TABLE IF NOT EXISTS faqs (
                    id SERIAL PRIMARY KEY,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    category VARCHAR(50) DEFAULT 'general',
                    views INTEGER DEFAULT 0,
                    helpful_count INTEGER NOT NULL DEFAULT 0,
                    not_helpful_count INTEGER NOT NULL DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    lang VARCHAR(8) NOT NULL DEFAULT 'fa',
                    UNIQUE(question, lang)
                );
                CREATE INDEX IF NOT EXISTS idx_faqs_category ON faqs (category) WHERE is_active = TRUE;
                CREATE UNIQUE INDEX IF NOT EXISTS idx_faqs_question_lang ON faqs (question, lang);
                """
                
                db.execute_query(create_sql_fixed)
                print("Table recreated with correct schema (using 'lang' column).")
            except Exception as e2:
                print(f"(X) Failed to reset table: {e2}")
                return

    # Now loop real seeding
    count = 0
    
    print("Starting seeding process...")
    for faq in defaults:
        try:
            # We use direct query to ensure we use 'lang'
            query = """
                INSERT INTO faqs (question, answer, category, lang)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (question, lang) DO NOTHING
            """
            result = db.execute_query(query, (faq['question'], faq['answer'], faq['category'], faq['lang']))
            print(f"(+) Added: {faq['question'][:20]}... ({faq['lang']})")
            count += 1
            
        except Exception as e:
            print(f"(X) Error adding item: {e}")

    print(f"Summary: Successfully processed {count} FAQs.")

if __name__ == "__main__":
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass
    asyncio.run(seed_faqs())
