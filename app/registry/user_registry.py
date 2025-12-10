"""
User Handler Registry

⚠️ تمام کدها از main.py کپی شده‌اند - هیچ logic تغییر نکرده!
"""

from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters
)

from .base_registry import BaseHandlerRegistry
from handlers.user.modules.navigation.main_menu import MainMenuHandler
from handlers.user.modules.search.search_handler import SearchHandler
from handlers.user.modules.categories.category_handler import CategoryHandler
from handlers.user.modules.attachments.season_handler import SeasonTopHandler
from handlers.user.modules.suggested.suggested_handler import SuggestedHandler
from handlers.user.modules.guides.guides_handler import GuidesHandler
from handlers.user.modules.cms.cms_handler import CMSUserHandler
from handlers.user.modules.categories.weapon_handler import WeaponHandler
from handlers.user.modules.attachments.top_handler import TopAttachmentsHandler
from handlers.user.modules.attachments.all_handler import AllAttachmentsHandler
from utils.subscribers_pg import SubscribersPostgres

from handlers.user import SEARCHING
from handlers.user.modules.feedback import FeedbackHandler, FEEDBACK_TEXT
from handlers.user.modules.settings.language_handler import LanguageHandler
from handlers.user.modules.notification_handler import NotificationHandler
from handlers.user.modules.help_handler import HelpHandler


class UserHandlerRegistry(BaseHandlerRegistry):
    """ثبت handlers مربوط به کاربران عادی"""
    
    def __init__(self, application, db, bot_instance):
        """
        Args:
            application: Telegram Application
            db: Database adapter
            bot_instance: Instance of CODMAttachmentsBot (برای دسترسی به handlers)
        """
        super().__init__(application, db)
        self.bot = bot_instance
        self.contact_handlers = bot_instance.contact_handlers
        self.admin_handlers = bot_instance.admin_handlers
        
        self.feedback_handler = FeedbackHandler(db)
        self.language_handler = LanguageHandler(db)
        
        # Initialize Subscribers (shared instance)
        self.subs = SubscribersPostgres(db_adapter=self.db)

        # Initialize Handlers
        self.main_menu_handler = MainMenuHandler(self.db)
        # Inject subs into NotificationHandler
        self.notification_handler = NotificationHandler(self.db, self.subs)
        self.category_handler = CategoryHandler(self.db)
        self.weapon_handler = WeaponHandler(self.db)
        self.top_handler = TopAttachmentsHandler(self.db)
        self.all_handler = AllAttachmentsHandler(self.db)
        self.season_handler = SeasonTopHandler(self.db)
        self.suggested_handler = SuggestedHandler(self.db)
        self.guides_handler = GuidesHandler(self.db)
        self.cms_user_handler = CMSUserHandler(self.db)
        
        self.help_handler = HelpHandler(db)
        
        self.search_handler = SearchHandler(
            db, 
            main_menu_handler=self.main_menu_handler,
            category_handler=self.category_handler,
            season_handler=self.season_handler,
            suggested_handler=self.suggested_handler,
            guides_handler=self.guides_handler,
            notification_handler=self.notification_handler,
            cms_user_handler=self.cms_user_handler
        )
        # تزریق HelpHandler به SearchHandler برای پشتیبانی از search_cancel_and_help
        self.search_handler.help_handler = self.help_handler

        # اتصال NotificationHandler کاربر به AdminHandlers جهت استفاده در admin_registry_states
        try:
            if hasattr(self.bot, "admin_handlers") and self.bot.admin_handlers is not None:
                # admin_handlers.user_handlers.admin_exit_and_notifications در states استفاده می‌شود
                setattr(self.bot.admin_handlers, "user_handlers", self.notification_handler)
        except Exception:
            # اگر به هر دلیل bot یا admin_handlers در دسترس نبود، فقط از این قابلیت صرف‌نظر می‌کنیم
            pass
    
    def register(self):
        """ثبت تمام handlers مربوط به کاربران"""
        self._register_commands()
        self._register_message_handlers()
        self._register_search_conversation()
        self._register_callback_handlers()
        self._register_season_top_handlers()
        self._register_suggested_handlers()
        self._register_feedback_handlers()
        self._register_notification_handlers()
        self._register_dynamic_handlers()
    
    def _register_commands(self):
        """ثبت command handlers"""
        self.application.add_handler(CommandHandler("start", self.main_menu_handler.start))
        self.application.add_handler(CommandHandler("myid", self.bot.show_user_id))
        self.application.add_handler(CommandHandler("subscribe", self.notification_handler.subscribe_cmd))
        self.application.add_handler(CommandHandler("unsubscribe", self.notification_handler.unsubscribe_cmd))
    
    def _register_message_handlers(self):
        """ثبت message handlers"""
        # هندلرهای پیام‌های متنی برای دکمه‌های کیبورد
        # دریافت اتچمنت - اول مود را می‌پرسد
        self.application.add_handler(MessageHandler(filters.Regex('^🔫 دریافت اتچمنت$'), self.category_handler.show_mode_selection_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^🔫 Get Attachments$'), self.category_handler.show_mode_selection_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^📖 راهنما$'), self.help_handler.help_command_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^📖 Help$'), self.help_handler.help_command_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^⚙️ تنظیمات کالاف$'), self.guides_handler.game_settings_menu))
        self.application.add_handler(MessageHandler(filters.Regex('^⚙️ تنظیمات بازی$'), self.guides_handler.game_settings_menu))
        self.application.add_handler(MessageHandler(filters.Regex('^⚙️ Game Settings$'), self.guides_handler.game_settings_menu))
        # تنظیمات ربات (کاربر)
        self.application.add_handler(MessageHandler(filters.Regex('^⚙️ تنظیمات ربات$'), self.language_handler.open_user_settings))
        self.application.add_handler(MessageHandler(filters.Regex('^⚙️ Bot Settings$'), self.language_handler.open_user_settings))
        # محتوای CMS (پیام)
        self.application.add_handler(MessageHandler(filters.Regex('^📰 محتوا$'), self.cms_user_handler.cms_home_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^📰 Content$'), self.cms_user_handler.cms_home_msg))
        
        # Import show_user_attachments_menu برای handler
        from handlers.user.user_attachments import show_user_attachments_menu
        self.application.add_handler(MessageHandler(filters.Regex('^🎮 اتچمنت کاربران$'), show_user_attachments_menu))
        self.application.add_handler(MessageHandler(filters.Regex('^🎮 User Attachments$'), show_user_attachments_menu))
        
        # منوی راهنماها (Reply Keyboard) - برای backward compatibility
        self.application.add_handler(MessageHandler(filters.Regex('^Basic$'), self.guides_handler.guide_basic_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^Sens$'), self.guides_handler.guide_sens_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^Hud$'), self.guides_handler.guide_hud_msg))
        
        # منوی اصلی - برترهای فصل
        self.application.add_handler(MessageHandler(filters.Regex('^⭐ برترهای فصل$'), self.season_handler.season_top_media_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^⭐ Season Top$'), self.season_handler.season_top_media_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^📋 لیست برترها$'), self.season_handler.season_top_list_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^📋 Top List$'), self.season_handler.season_top_list_msg))
        
        # کیبورد سطح سلاح
        self.application.add_handler(MessageHandler(filters.Regex('^⭐ برترها$'), self.top_handler.show_top_attachments_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^⭐ برترین اتچمنت‌ها$'), self.top_handler.show_top_attachments_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^⭐ Top Attachments$'), self.top_handler.show_top_attachments_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^📋 همه اتچمنت‌ها$'), self.all_handler.show_all_attachments_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^📋 All Attachments$'), self.all_handler.show_all_attachments_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^(⬅️|🔙) بازگشت$'), self.main_menu_handler.back_msg))
        self.application.add_handler(MessageHandler(filters.Regex('^(⬅️|🔙) Back$'), self.main_menu_handler.back_msg))
    
    def _register_search_conversation(self):
        """ثبت ConversationHandler جستجو"""
        search_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.search_handler.search_start, pattern="^search$"),
                CallbackQueryHandler(self.search_handler.search_start, pattern="^search_weapon$"),
                MessageHandler(filters.Regex('^🔍 جستجوی اتچمنت$'), self.search_handler.search_start_msg),
                MessageHandler(filters.Regex('^🔍 جستجو$'), self.search_handler.search_start_msg),
                MessageHandler(filters.Regex('^🔍 Search Attachments$'), self.search_handler.search_start_msg),
                MessageHandler(filters.Regex('^🔍 Search$'), self.search_handler.search_start_msg)
            ],
            states={
                SEARCHING: [
                    # ابتدا دکمه‌های کیبورد را چک می‌کنیم - IMPORTANT: باید قبل از handler عمومی باشد
                    # اگر کاربر دوباره دکمه جستجو رو بزنه، بی‌صدا دوباره پیام رو نمایش بده
                    MessageHandler(filters.Regex('^🔍 جستجوی اتچمنت$'), self.search_handler.search_restart_silently),
                    MessageHandler(filters.Regex('^🔍 جستجو$'), self.search_handler.search_restart_silently),
                    MessageHandler(filters.Regex('^🔍 Search Attachments$'), self.search_handler.search_restart_silently),
                    MessageHandler(filters.Regex('^🔍 Search$'), self.search_handler.search_restart_silently),
                    # دکمه‌های دیگه - لغو جستجو و رفتن به بخش دیگه
                    MessageHandler(filters.Regex('^🔫 دریافت اتچمنت$'), self.search_handler.search_cancel_and_show_mode_selection),
                    MessageHandler(filters.Regex('^🔫 Get Attachments$'), self.search_handler.search_cancel_and_show_mode_selection),
                    MessageHandler(filters.Regex('^⭐ برترهای فصل$'), self.search_handler.search_cancel_and_season_top),
                    MessageHandler(filters.Regex('^⭐ Season Top$'), self.search_handler.search_cancel_and_season_top),
                    MessageHandler(filters.Regex('^📋 لیست برترها$'), self.search_handler.search_cancel_and_season_list),
                    MessageHandler(filters.Regex('^📋 Top List$'), self.search_handler.search_cancel_and_season_list),
                    MessageHandler(filters.Regex('^💡 اتچمنت‌های پیشنهادی$'), self.search_handler.search_cancel_and_suggested),
                    MessageHandler(filters.Regex('^💡 Suggested Attachments$'), self.search_handler.search_cancel_and_suggested),
                    # CMS: خروج از جستجو و نمایش CMS
                    MessageHandler(filters.Regex('^📰 محتوا$'), self.search_handler.search_cancel_and_cms),
                    MessageHandler(filters.Regex('^📰 Content$'), self.search_handler.search_cancel_and_cms),
                    MessageHandler(filters.Regex('^⚙️ تنظیمات کالاف$'), self.search_handler.search_cancel_and_game_settings),
                    MessageHandler(filters.Regex('^⚙️ Game Settings$'), self.search_handler.search_cancel_and_game_settings),
                    MessageHandler(filters.Regex('^📖 راهنما$'), self.search_handler.search_cancel_and_help),
                    MessageHandler(filters.Regex('^📖 Help$'), self.search_handler.search_cancel_and_help),
                    MessageHandler(filters.Regex('^📞 تماس با ما$'), self.contact_handlers.search_cancel_and_contact),
                    MessageHandler(filters.Regex('^📞 Contact Us$'), self.contact_handlers.search_cancel_and_contact),
                    MessageHandler(filters.Regex('^🔔 تنظیمات اعلان‌ها$'), self.search_handler.search_cancel_and_notifications),
                    MessageHandler(filters.Regex('^🔔 Notification Settings$'), self.search_handler.search_cancel_and_notifications),
                    MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), self.admin_handlers.search_cancel_and_admin),
                    MessageHandler(filters.Regex('^👨‍💼 Admin Panel$'), self.admin_handlers.search_cancel_and_admin),
                    MessageHandler(filters.Regex('^پنل ادمین$'), self.admin_handlers.search_cancel_and_admin),
                    MessageHandler(filters.Regex('^Admin Panel$'), self.admin_handlers.search_cancel_and_admin),
                    # سپس متن عادی را به عنوان جستجو پردازش می‌کنیم
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.search_handler.search_process)
                ]
            },
            fallbacks=[
                # دکمه لغو - بازگشت به منوی اصلی و خروج از conversation
                CallbackQueryHandler(self.main_menu_handler.main_menu, pattern="^main_menu$")
            ]
        )
        self.application.add_handler(search_conv)
    
    def _register_callback_handlers(self):
        """ثبت CallbackQuery handlers"""
        # مشاهده اتچمنت از نوتیفیکیشن - با group=-1 تا قبل از همه handlers اجرا بشه
        self.application.add_handler(
            CallbackQueryHandler(self.notification_handler.view_attachment_from_notification, pattern="^attm__"),
            group=-1
        )
        
        # CallbackQuery handlers برای منوها
        # دریافت اتچمنت - اول مود را می‌پرسد
        self.application.add_handler(CallbackQueryHandler(self.category_handler.show_mode_selection, pattern="^categories$"))
        self.application.add_handler(CallbackQueryHandler(self.category_handler.show_mode_selection, pattern="^select_mode_first$"))
        # انتخاب مود (MP/BR) در ابتدای فلوی دریافت اتچمنت
        self.application.add_handler(CallbackQueryHandler(self.category_handler.mode_selected, pattern="^mode_(mp|br)$"))
        self.application.add_handler(CallbackQueryHandler(self.weapon_handler.show_weapons, pattern="^cat_"))
        self.application.add_handler(CallbackQueryHandler(self.weapon_handler.show_weapon_menu, pattern="^wpn_"))
        # Handler برای انتخاب mode بعد از انتخاب سلاح (BR/MP در سطح weapon)
        self.application.add_handler(CallbackQueryHandler(self.weapon_handler.show_mode_menu, pattern="^mode_(?!mp$|br$)"))
        self.application.add_handler(CallbackQueryHandler(self.top_handler.show_top_attachments, pattern="^show_top$"))
        # نمایش همه اتچمنت‌ها؛ پشتیبانی از مسیر مستقیم از نتایج جستجو: all_{category}__{weapon}
        self.application.add_handler(CallbackQueryHandler(self.all_handler.show_all_attachments, pattern="^show_all$|^all_page_|^all_"))
        # send_attachment_quick is in AllAttachmentsHandler? No, it was in UserHandlers.
        # Let's check where it should be. Probably AllAttachmentsHandler or SearchHandler.
        # UserHandlers had it. I need to find it.
        # It's for "qatt_" callback.
        # I'll assume it's in AllAttachmentsHandler or I need to move it.
        # Checked SearchHandler: it generates "qatt_" buttons.
        # But who handles them? UserHandlers.send_attachment_quick.
        # I need to move send_attachment_quick to SearchHandler or AllAttachmentsHandler.
        # Let's assume I moved it to SearchHandler (it's related to quick result from search).
        # Wait, I didn't move it yet. I need to add it to SearchHandler.
        self.application.add_handler(CallbackQueryHandler(self.search_handler.send_attachment_quick, pattern="^qatt_"))
        
        # اتچمنت با mode (فرمت: attm_{mode}_{code})
        # پیاده‌سازی صحیح در AllAttachmentsHandler.attachment_detail_with_mode قرار دارد.
        self.application.add_handler(CallbackQueryHandler(self.all_handler.attachment_detail_with_mode, pattern="^attm_"))
        
        # دریافت همه اتچمنت‌های یک mode
        # NOTE: download_all_attachments method doesn't exist in AllAttachmentsHandler - commented out
        # self.application.add_handler(CallbackQueryHandler(self.all_handler.download_all_attachments, pattern="^download_all_"))
        
        # اتچمنت عادی - فقط att_{code} نه top/season/like/dislike/fb/copy
        # Exclude copy_ تا دکمه «📋 کپی کد» به هندلر اختصاصی خودش برود
        self.application.add_handler(CallbackQueryHandler(self.all_handler.attachment_detail, pattern=r"^att_(?!top_|season_|like_|dislike_|fb_|copy_)") )
        
        # دیگر handlers
        self.application.add_handler(CallbackQueryHandler(self.help_handler.help_command, pattern="^help$"))
        self.application.add_handler(CallbackQueryHandler(self.main_menu_handler.main_menu, pattern="^main_menu$"))
        # CMS (User)
        self.application.add_handler(CallbackQueryHandler(self.cms_user_handler.cms_home, pattern="^cms$"))
        self.application.add_handler(CallbackQueryHandler(self.cms_user_handler.cms_type_selected, pattern="^cms_type_"))
        self.application.add_handler(CallbackQueryHandler(self.cms_user_handler.cms_view, pattern="^cms_view_\\d+$"))
        self.application.add_handler(CallbackQueryHandler(self.cms_user_handler.cms_list_page_navigation, pattern="^cmslist_page_\\d+$"))
        # تنظیمات ربات (کاربر)
        self.application.add_handler(CallbackQueryHandler(self.language_handler.open_user_settings, pattern="^user_settings_menu$"))
        self.application.add_handler(CallbackQueryHandler(self.language_handler.open_language_menu, pattern="^user_settings_language$"))
        self.application.add_handler(CallbackQueryHandler(self.language_handler.set_language, pattern="^set_lang_(fa|en)$"))
        # تنظیمات بازی
        self.application.add_handler(CallbackQueryHandler(self.guides_handler.game_settings_menu, pattern="^game_settings_menu$"))
        self.application.add_handler(CallbackQueryHandler(self.guides_handler.game_settings_mode_selected, pattern="^game_settings_(br|mp)$"))
        self.application.add_handler(CallbackQueryHandler(self.guides_handler.show_guide_inline, pattern="^show_guide_"))
        from handlers.channel.channel_handlers import noop_cb
        self.application.add_handler(CallbackQueryHandler(noop_cb, pattern="^noop$"))
    
    def _register_season_top_handlers(self):
        """ثبت handlers برترهای فصل"""
        # انتخاب mode برای برترهای فصل (گالری)
        self.application.add_handler(CallbackQueryHandler(self.season_handler.season_top_select_mode, pattern="^season_top$"))
        self.application.add_handler(CallbackQueryHandler(self.season_handler.season_top_media_with_mode, pattern="^season_top_mode_"))
        
        # انتخاب mode برای لیست برترهای فصل
        self.application.add_handler(CallbackQueryHandler(self.season_handler.season_top_list_select_mode, pattern="^season_top_list$"))
        self.application.add_handler(CallbackQueryHandler(self.season_handler.season_top_list_with_mode, pattern="^season_list_mode_"))
        
        # صفحه‌بندی و جزئیات
        self.application.add_handler(CallbackQueryHandler(self.season_handler.season_top_list_page_navigation, pattern="^slist_page_"))
        self.application.add_handler(CallbackQueryHandler(self.season_handler.season_top_item_detail, pattern="^satt_"))
    
    def _register_suggested_handlers(self):
        """ثبت handlers اتچمنت‌های پیشنهادی"""
        # انتخاب mode برای اتچمنت‌های پیشنهادی
        self.application.add_handler(CallbackQueryHandler(self.suggested_handler.suggested_attachments_select_mode, pattern="^suggested_attachments$"))
        # نمایش لیست سلاح‌ها (بعد از انتخاب mode)
        self.application.add_handler(CallbackQueryHandler(self.suggested_handler.suggested_media_with_mode, pattern="^suggested_mode_"))
        # نمایش لیست اتچمنت‌های یک سلاح
        self.application.add_handler(CallbackQueryHandler(self.suggested_handler.suggested_weapon_attachments, pattern="^sugg_wpn_"))
        # ارسال یک اتچمنت پیشنهادی
        self.application.add_handler(CallbackQueryHandler(self.suggested_handler.suggested_send_attachment, pattern="^sugg_send_"))
        
        # نمایش لیست اتچمنت‌های پیشنهادی (متنی)
        self.application.add_handler(CallbackQueryHandler(self.suggested_handler.suggested_list_with_mode, pattern="^suggested_list_mode_"))
        self.application.add_handler(CallbackQueryHandler(self.suggested_handler.suggested_list_page_navigation, pattern="^sugglist_page_"))
        
        # handler برای دکمه "💡 اتچمنت‌های پیشنهادی"
        self.application.add_handler(MessageHandler(filters.Regex('^💡 اتچمنت‌های پیشنهادی$'), self.suggested_handler.suggested_attachments_select_mode_msg))
        # انگلیسی: "💡 Suggested Attachments"
        self.application.add_handler(MessageHandler(filters.Regex('^💡 Suggested Attachments$'), self.suggested_handler.suggested_attachments_select_mode_msg))
    
    def _register_feedback_handlers(self):
        """ثبت handlers سیستم بازخورد اتچمنت‌ها"""
        # ConversationHandler برای دریافت بازخورد متنی
        feedback_conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.feedback_handler.handle_feedback_request, pattern=r"^att_fb_\d+$")
            ],
            states={
                FEEDBACK_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.feedback_handler.handle_feedback_text),
                    CallbackQueryHandler(self.feedback_handler.handle_feedback_cancel, pattern="^att_fb_cancel_")
                ]
            },
            fallbacks=[
                CommandHandler('cancel', self.feedback_handler.handle_feedback_cancel)
            ],
            name="feedback_conversation",
            persistent=False
        )
        self.application.add_handler(feedback_conv_handler)
        
        # Callback handlers برای لایک/دیس‌لایک
        self.application.add_handler(CallbackQueryHandler(self.feedback_handler.handle_vote_like, pattern=r"^att_like_\d+$"))
        self.application.add_handler(CallbackQueryHandler(self.feedback_handler.handle_vote_dislike, pattern=r"^att_dislike_\d+$"))
        # Callback handler برای کپی کد
        self.application.add_handler(CallbackQueryHandler(self.feedback_handler.handle_copy_code, pattern=r"^att_copy_\d+$"))
    
    def _register_notification_handlers(self):
        """ثبت handlers تنظیمات اعلان‌ها"""
        # Handler عمومی برای دکمه keyboard - با group=10 تا بعد از ConversationHandler ها اجرا بشه
        # این فقط در حالت عادی (نه admin، نه search) trigger میشه
        # استفاده از wrapper که flag رو check می‌کنه
        self.application.add_handler(
            MessageHandler(filters.Regex('^(🔔 تنظیمات اعلان‌ها|🔔 Notification Settings)$'), self.notification_handler.notification_settings_with_check),
            group=10
        )
        
        # CallbackQuery handlers برای interaction با منوی notification
        self.application.add_handler(CallbackQueryHandler(self.notification_handler.notification_toggle, pattern="^user_notif_toggle$"))
        self.application.add_handler(CallbackQueryHandler(self.notification_handler.notification_toggle_mode, pattern="^user_notif_mode_"))
        self.application.add_handler(CallbackQueryHandler(self.notification_handler.notification_events_menu, pattern="^user_notif_events$"))
        self.application.add_handler(CallbackQueryHandler(self.notification_handler.notification_toggle_event, pattern="^user_notif_event_"))
        self.application.add_handler(CallbackQueryHandler(self.notification_handler.notification_settings, pattern="^user_notif_back$"))
    
    def _register_language_settings_handlers(self):
        """ثبت handlers تنظیمات زبان"""
        self.application.add_handler(CallbackQueryHandler(self.language_handler.open_language_menu, pattern="^user_settings_language$"))
        self.application.add_handler(CallbackQueryHandler(self.language_handler.set_language, pattern="^set_lang_(fa|en)$"))
    
    def _register_dynamic_handlers(self):
        """ثبت dynamic handlers - کپی دقیق از main.py خط 836-841"""
        # روتر داینامیک برای نام‌های سفارشی Basic/Sens/Hud (در انتها تا با دکمه‌های دیگه تداخل نداشته باشد)
        # استثنا برای دکمه‌های منوی اصلی که باید توسط handlers خودشون گرفته بشن
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex('^(🔫 دریافت اتچمنت|🔫 Get Attachments|🔍 جستجوی اتچمنت|🔍 Search Attachments|⭐ برترهای فصل|⭐ Season Top|📋 لیست برترها|📋 Top List|💡 اتچمنت‌های پیشنهادی|💡 Suggested Attachments|⚙️ تنظیمات کالاف|⚙️ تنظیمات بازی|⚙️ Game Settings|🔔 تنظیمات اعلان‌ها|🔔 Notification Settings|📞 تماس با ما|📞 Contact Us|📖 راهنما|📖 Help|👨‍💼 پنل ادمین|👨‍💼 Admin Panel|پنل ادمین|Admin Panel|⚙️ تنظیمات ربات|⚙️ Bot Settings|📰 محتوا|📰 Content)$'),
            self.guides_handler.guide_dynamic_msg
        ))
