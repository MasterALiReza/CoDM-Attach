"""
Admin Handler Registry

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
from handlers.admin.modules.feedback import FeedbackAdminHandler


class AdminHandlerRegistry(BaseHandlerRegistry):
    """ثبت handlers مربوط به ادمین"""
    
    def __init__(self, application, db, bot_instance):
        """
        Args:
            application: Telegram Application
            db: Database adapter
            bot_instance: Instance of CODMAttachmentsBot
        """
        super().__init__(application, db)
        self.bot = bot_instance
        self.admin_handlers = bot_instance.admin_handlers
        # self.user_handlers = bot_instance.user_handlers  # TODO: Fix - user_handlers doesn't exist
        self.user_handlers = None  # Temporary fix
        self.feedback_admin = FeedbackAdminHandler(db)
    
    def register(self):
        """ثبت تمام handlers ادمین - کپی دقیق از main.py"""
        self._register_admin_conversation()
        self._register_feedback_dashboard()
    
    def _register_admin_conversation(self):
        """
        ثبت ConversationHandler ادمین - کپی دقیق از main.py خط 178-676
        
        ⚠️ این تابع تمام admin conversation را از main.py کپی می‌کند
        ⚠️ هیچ تغییری در logic نداده است
        """
        # Import states helper
        from .admin_registry_states import get_admin_conversation_states
        
        # Import admin states
        from handlers.admin.admin_states import (
            ADMIN_MENU, ADD_WEAPON_NAME,
            ADD_ATTACHMENT_CATEGORY, ADD_ATTACHMENT_WEAPON, ADD_ATTACHMENT_MODE, ADD_ATTACHMENT_CODE,
            ADD_ATTACHMENT_NAME, ADD_ATTACHMENT_IMAGE, ADD_ATTACHMENT_TOP, ADD_ATTACHMENT_SEASON,
            DELETE_ATTACHMENT_CATEGORY, DELETE_ATTACHMENT_WEAPON, DELETE_ATTACHMENT_MODE, DELETE_ATTACHMENT_SELECT,
            SET_TOP_CATEGORY, SET_TOP_WEAPON, SET_TOP_MODE, SET_TOP_SELECT, SET_TOP_CONFIRM,
            IMPORT_FILE, IMPORT_MODE, EXPORT_TYPE,
            EDIT_ATTACHMENT_CATEGORY, EDIT_ATTACHMENT_WEAPON, EDIT_ATTACHMENT_MODE, EDIT_ATTACHMENT_SELECT,
            EDIT_ATTACHMENT_ACTION, EDIT_ATTACHMENT_NAME, EDIT_ATTACHMENT_IMAGE, EDIT_ATTACHMENT_CODE,
            ADD_ADMIN_ID, ADD_ADMIN_DISPLAY_NAME, REMOVE_ADMIN_ID, EDIT_ADMIN_SELECT,
            NOTIF_COMPOSE, NOTIF_CONFIRM,
            TEXT_EDIT,
            GUIDE_RENAME, GUIDE_ADD_PHOTO, GUIDE_ADD_VIDEO, GUIDE_SET_CODE,
            GUIDE_MEDIA_CONFIRM, GUIDE_FINAL_CONFIRM,
            WEAPON_SELECT_CATEGORY, WEAPON_SELECT_WEAPON, WEAPON_ACTION_MENU, WEAPON_DELETE_CONFIRM, WEAPON_DELETE_MODE,
            TICKET_REPLY, TICKET_SEARCH,
            ADD_FAQ_QUESTION, ADD_FAQ_ANSWER, ADD_FAQ_CATEGORY,
            EDIT_FAQ_SELECT, EDIT_FAQ_QUESTION, EDIT_FAQ_ANSWER,
            DIRECT_CONTACT_NAME, DIRECT_CONTACT_LINK,
            MANAGE_SUGGESTED_MENU, MANAGE_SUGGESTED_MODE, MANAGE_SUGGESTED_ADD,
            MANAGE_SUGGESTED_ADD_CATEGORY, MANAGE_SUGGESTED_ADD_WEAPON, MANAGE_SUGGESTED_ADD_ATTACHMENT,
            MANAGE_SUGGESTED_ADD_PRIORITY, MANAGE_SUGGESTED_ADD_REASON,
            MANAGE_SUGGESTED_REMOVE_SELECT,
            AWAITING_BACKUP_FILE
        )
        
        # ساخت ConversationHandler - دقیقاً مثل main.py
        admin_conv = ConversationHandler(
            entry_points=[
                CommandHandler("admin", self.admin_handlers.admin_start),
                MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), self.admin_handlers.admin_start_msg),
                MessageHandler(filters.Regex('^.*Admin Panel$'), self.admin_handlers.admin_start_msg),
                MessageHandler(filters.Regex('^پنل ادمین$'), self.admin_handlers.admin_start_msg),
                MessageHandler(filters.Regex('^Admin Panel$'), self.admin_handlers.admin_start_msg),
                CallbackQueryHandler(self.admin_handlers.admin_menu_return, pattern="^admin_return$"),
                CallbackQueryHandler(self.admin_handlers.admin_menu, pattern="^admin_")
            ],
            states=get_admin_conversation_states(self.admin_handlers),
            fallbacks=[
                CallbackQueryHandler(self.admin_handlers.admin_menu, pattern="^admin_exit$"),
                CallbackQueryHandler(self.admin_handlers.admin_menu_return, pattern="^admin_cancel$"),
                CallbackQueryHandler(self.admin_handlers.admin_menu_return, pattern="^admin_back$"),
                CallbackQueryHandler(self.admin_handlers.admin_menu_return, pattern="^admin_menu_return$")
            ],
            per_message=False,
            per_chat=True,
            per_user=True,
            name="admin_conversation"
        )
        
        self.application.add_handler(admin_conv, group=-1)
    
    def _register_feedback_dashboard(self):
        """ثبت handlers داشبورد بازخورد"""
        # Main dashboard
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.show_feedback_dashboard, 
            pattern="^fb_dashboard$"
        ))
        
        # Reports
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.show_top_attachments, 
            pattern="^fb_top$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.show_bottom_attachments, 
            pattern="^fb_bottom$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.show_user_comments, 
            pattern="^fb_comments$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.show_detailed_stats, 
            pattern="^fb_detailed$"
        ))
        # Search
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.show_search_menu, 
            pattern="^fb_search$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.execute_search_query, 
            pattern="^fb_search_q_"
        ))
        
        # Pagination for comments
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.show_user_comments, 
            pattern="^fb_comments_page_"
        ))
        
        # Period selection
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.change_period, 
            pattern="^fb_change_period$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.set_period, 
            pattern="^fb_period_"
        ))
        # Suggested-only toggle
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.toggle_suggested_only,
            pattern="^fb_toggle_suggested$"
        ))
        # Filters: mode
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.filter_mode_menu,
            pattern="^fb_filter_mode$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.set_mode_filter,
            pattern="^fb_mode_(br|mp|all)$"
        ))
        # Filters: category
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.filter_category_menu,
            pattern="^fb_filter_category$"
        ))
        self.application.add_handler(CallbackQueryHandler(
            self.feedback_admin.set_category_filter,
            pattern="^fb_cat_"
        ))
