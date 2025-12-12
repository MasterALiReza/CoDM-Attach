import sys
import os
import asyncio
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

from core.database.database_pg_proxy import DatabasePostgresProxy
from config.config import POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT

async def seed_faqs():
    print("Connecting to database...")
    db = DatabasePostgresProxy()
    
    # Check if we have FAQs
    faqs_fa = db.get_faqs(lang='fa')
    faqs_en = db.get_faqs(lang='en')
    
    if faqs_fa or faqs_en:
        print(f"FAQs already exist. (FA: {len(faqs_fa)}, EN: {len(faqs_en)})")
        print("Skipping seed.")
        return

    print("No FAQs found. Seeding defaults...")
    
    # Default FAQs
    defaults = [
        # FA
        {
            "question": "چگونه از ربات استفاده کنم؟",
            "answer": "از منوی اصلی، **مود بازی** (بتل رویال یا مولتی پلیر) را انتخاب کنید. سپس دسته سلاح و خود سلاح را انتخاب کنید تا بهترین اتچمنت‌ها نمایش داده شوند.",
            "lang": "fa"
        },
        {
            "question": "چگونه اتچمنت خود را ثبت کنم؟",
            "answer": "از منوی اصلی وارد بخش **🎮 اتچمنت کاربران** شوید و دکمه **📤 ارسال اتچمنت** را بزنید. سپس طبق راهنما، نام، عکس و کد اتچمنت خود را بفرستید.",
            "lang": "fa"
        },
        {
            "question": "چرا اتچمنت من هنوز نمایش داده نشده؟",
            "answer": "اتچمنت‌های ارسالی کاربران باید توسط **ادمین‌ها** بررسی و تایید شوند. این فرآیند ممکن است کمی زمان ببرد. پس از تایید یا رد، به شما اطلاع داده می‌شود.",
            "lang": "fa"
        },
        {
            "question": "چگونه با پشتیبانی تماس بگیرم؟",
            "answer": "از منوی اصلی دکمه **📞 تماس با ما** را انتخاب کنید. می‌توانید **تیکت** ثبت کنید یا پیشنهاد/انتقاد خود را بفرستید.",
            "lang": "fa"
        },
        # EN
        {
            "question": "How to use the bot?",
            "answer": "Select your **Game Mode** (Battle Royale or Multiplayer) from the main menu. Then choose a weapon category and weapon to see the best attachments.",
            "lang": "en"
        },
        {
            "question": "How to submit my own attachment?",
            "answer": "Go to **🎮 User Attachments** from the main menu and click **📤 Submit Attachment**. Follow the instructions to send your attachment name, image, and code.",
            "lang": "en"
        },
        {
            "question": "Why is my attachment pending?",
            "answer": "All user submissions must be **approved by admins** before being published. You will be notified once your attachment is approved or rejected.",
            "lang": "en"
        },
         {
            "question": "How to contact support?",
            "answer": "Select **📞 Contact Us** from the main menu. You can submit a **Ticket** or send feedback.",
            "lang": "en"
        }
    ]
    
    count = 0
    for faq in defaults:
        try:
            db.add_faq(faq['question'], faq['answer'], faq['lang'])
            count += 1
            print(f"Added FAQ: {faq['question']} ({faq['lang']})")
        except Exception as e:
            print(f"Error adding FAQ: {e}")

    print(f"✅ Successfully seeded {count} FAQs.")

if __name__ == "__main__":
    asyncio.run(seed_faqs())
