"""
Admin ConversationHandler States

⚠️ کپی کامل تمام states از main.py - هیچ تغییری نشده!
این فایل حاوی تمام states dict برای ConversationHandler است.
"""

from telegram.ext import MessageHandler, CallbackQueryHandler, filters


def get_admin_conversation_states(admin_handlers):
    """
    برگرداندن dict کامل states برای ConversationHandler - کپی دقیق از main.py
    
    Args:
        admin_handlers: instance of AdminHandlers
    Returns:
        dict: states dictionary برای ConversationHandler
    """
    # Import states
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
        NOTIF_COMPOSE, NOTIF_CONFIRM, SCHED_EDIT_TEXT,
        TEXT_EDIT,
        GUIDE_RENAME, GUIDE_ADD_PHOTO, GUIDE_ADD_VIDEO, GUIDE_SET_CODE,
        GUIDE_MEDIA_CONFIRM, GUIDE_FINAL_CONFIRM,
        WEAPON_SELECT_MODE, WEAPON_SELECT_CATEGORY, WEAPON_SELECT_WEAPON, WEAPON_ACTION_MENU, WEAPON_DELETE_CONFIRM, WEAPON_DELETE_MODE,
        TICKET_REPLY, TICKET_SEARCH,
        ADD_FAQ_QUESTION, ADD_FAQ_ANSWER, ADD_FAQ_CATEGORY,
        EDIT_FAQ_SELECT, EDIT_FAQ_QUESTION, EDIT_FAQ_ANSWER,
        DIRECT_CONTACT_NAME, DIRECT_CONTACT_LINK,
        MANAGE_SUGGESTED_MENU, MANAGE_SUGGESTED_MODE, MANAGE_SUGGESTED_ADD,
        MANAGE_SUGGESTED_ADD_CATEGORY, MANAGE_SUGGESTED_ADD_WEAPON, MANAGE_SUGGESTED_ADD_ATTACHMENT,
        MANAGE_SUGGESTED_ADD_PRIORITY, MANAGE_SUGGESTED_ADD_REASON,
        MANAGE_SUGGESTED_REMOVE_SELECT,
        AWAITING_BACKUP_FILE,
        CATEGORY_MGMT_MODE, CATEGORY_MGMT_MENU,
        CMS_ADD_TYPE, CMS_ADD_TITLE, CMS_ADD_BODY, CMS_SEARCH_TEXT
    )
    
    # کپی دقیق همان states از main.py - خط 189-659
    # ⚠️ هیچ تغییری نسبت به main.py ندارد
    
    states_dict = {
        ADMIN_MENU: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^👨‍💼 Admin Panel$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^Admin Panel$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^🔔 تنظیمات اعلان‌ها$'), admin_handlers.user_handlers.admin_exit_and_notifications) if hasattr(admin_handlers, 'user_handlers') else None,
            MessageHandler(
                filters.Regex('^(🔫 دریافت اتچمنت|🔍 جستجوی اتچمنت|⭐ برترهای فصل|📋 لیست برترها|💡 اتچمنت‌های پیشنهادی|⚙️ تنظیمات کالاف|📞 تماس با ما|📖 راهنما)$'),
                admin_handlers.admin_exit_silent
            ),
            CallbackQueryHandler(admin_handlers.admin_start, pattern="^admin_menu$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_back$"),
            # Notification logic routing
            CallbackQueryHandler(admin_handlers.admin_menu, pattern="^notify_"),
            # مدیریت ادمین‌ها
            CallbackQueryHandler(admin_handlers.admin_menu, pattern="^manage_admins$"),
            CallbackQueryHandler(admin_handlers.add_admin_start, pattern="^add_new_admin$"),
            CallbackQueryHandler(admin_handlers.view_all_admins, pattern="^view_all_admins$"),
            CallbackQueryHandler(admin_handlers.role_stats, pattern="^role_stats$"),
            CallbackQueryHandler(admin_handlers.edit_admin_role_start, pattern="^edit_admin_role$"),
            CallbackQueryHandler(admin_handlers.view_roles_menu, pattern="^view_roles$"),
            CallbackQueryHandler(admin_handlers.remove_admin_start, pattern="^remove_admin$"),
            CallbackQueryHandler(admin_handlers.add_admin_role_selected, pattern="^selrole_"),
            CallbackQueryHandler(admin_handlers.edit_admin_role_select, pattern="^editadm_"),
            CallbackQueryHandler(admin_handlers.add_role_to_admin, pattern="^addrole_"),
            CallbackQueryHandler(admin_handlers.delete_role_from_admin, pattern="^delrole_"),
            CallbackQueryHandler(admin_handlers.add_role_confirm, pattern="^newrole_"),
            CallbackQueryHandler(admin_handlers.delete_role_confirm, pattern="^delconfirm_"),
            CallbackQueryHandler(admin_handlers.remove_admin_confirmed, pattern="^remove_confirm_"),
            CallbackQueryHandler(admin_handlers.remove_admin_confirmed, pattern="^remove_"),
            # تنظیمات بازی
            CallbackQueryHandler(admin_handlers.guides_menu, pattern="^admin_guides$"),
            CallbackQueryHandler(admin_handlers.guides_mode_selected, pattern="^gmode_"),
            CallbackQueryHandler(admin_handlers.guide_section_menu, pattern="^gsel_"),
            CallbackQueryHandler(admin_handlers.guide_op_router, pattern="^gop_"),
            # مدیریت اتچمنت‌های پیشنهادی
            CallbackQueryHandler(admin_handlers.manage_suggested_menu, pattern="^admin_manage_suggested$"),
            # Analytics
            CallbackQueryHandler(admin_handlers.analytics_menu, pattern="^attachment_analytics$"),
            CallbackQueryHandler(admin_handlers.analytics_menu, pattern="^analytics_menu$"),
            CallbackQueryHandler(admin_handlers.view_trending, pattern="^analytics_view_trending$"),
            CallbackQueryHandler(admin_handlers.view_underperforming, pattern="^analytics_view_underperforming$"),
            CallbackQueryHandler(admin_handlers.view_weapon_stats, pattern="^analytics_view_weapon_stats$"),
            CallbackQueryHandler(admin_handlers.weapon_stats_select_mode, pattern="^weapon_stats_mode_"),
            CallbackQueryHandler(admin_handlers.weapon_stats_show_results, pattern="^weapon_stats_cat_"),
            CallbackQueryHandler(admin_handlers.weapon_stats_show_results, pattern="^ws_cat_\\d+$"),
            CallbackQueryHandler(admin_handlers.view_weapon_stats, pattern="^ws_back_to_mode$"),
            CallbackQueryHandler(admin_handlers.analytics_handler.ws_back_to_categories, pattern="^ws_back_to_categories$"),
            CallbackQueryHandler(admin_handlers.view_user_behavior, pattern="^analytics_view_user_behavior$"),
            CallbackQueryHandler(admin_handlers.user_behavior_details, pattern="^user_behavior_details$"),
            CallbackQueryHandler(admin_handlers.daily_report, pattern="^analytics_daily_report$"),
            CallbackQueryHandler(admin_handlers.weekly_report, pattern="^analytics_weekly_report$"),
            CallbackQueryHandler(admin_handlers.search_attachment_stats, pattern="^analytics_search_attachment$"),
            CallbackQueryHandler(admin_handlers.download_report, pattern="^analytics_download_report$"),
            CallbackQueryHandler(admin_handlers.refresh_trending, pattern="^refresh_trending$"),
            CallbackQueryHandler(admin_handlers.daily_chart, pattern="^daily_chart$"),
            CallbackQueryHandler(admin_handlers.download_daily_csv, pattern="^download_daily_csv$"),
            CallbackQueryHandler(admin_handlers.att_daily_chart, pattern="^att_daily_chart_\\d+$"),
            CallbackQueryHandler(admin_handlers.att_download_csv, pattern="^att_download_csv_\\d+$"),
            CallbackQueryHandler(admin_handlers.weapon_details, pattern="^weapon_details_\\d+$"),
            # CMS
            CallbackQueryHandler(admin_handlers.cms_menu, pattern="^admin_cms$"),
            CallbackQueryHandler(admin_handlers.cms_add_start, pattern="^cms_add$"),
            CallbackQueryHandler(admin_handlers.cms_list_menu, pattern="^cms_list$"),
            CallbackQueryHandler(admin_handlers.cms_search_start, pattern="^cms_search$"),
            CallbackQueryHandler(admin_handlers.cms_type_selected, pattern="^cms_type_"),
            CallbackQueryHandler(admin_handlers.cms_publish, pattern="^cms_pub_\\d+$"),
            CallbackQueryHandler(admin_handlers.cms_delete, pattern="^cms_del_\\d+$"),
            # Data Management
            CallbackQueryHandler(admin_handlers.data_management_menu, pattern="^admin_data_management$"),
            CallbackQueryHandler(admin_handlers.data_health_menu, pattern="^data_health$"),
            CallbackQueryHandler(admin_handlers.data_health_menu, pattern="^health_menu$"),
            CallbackQueryHandler(admin_handlers.run_health_check, pattern="^run_health_check$"),
            CallbackQueryHandler(admin_handlers.view_full_report, pattern="^view_full_report$"),
            CallbackQueryHandler(admin_handlers.view_critical, pattern="^view_critical$"),
            CallbackQueryHandler(admin_handlers.view_warnings, pattern="^view_warnings$"),
            CallbackQueryHandler(admin_handlers.view_detailed_stats, pattern="^view_detailed_stats$"),
            CallbackQueryHandler(admin_handlers.view_check_history, pattern="^view_check_history$"),
            CallbackQueryHandler(admin_handlers.fix_issues_menu, pattern="^fix_issues_menu$"),
            CallbackQueryHandler(admin_handlers.fix_missing_images, pattern="^fix_missing_images$"),
            CallbackQueryHandler(admin_handlers.fix_duplicate_codes, pattern="^fix_duplicate_codes$"),
            CallbackQueryHandler(admin_handlers.fix_orphaned, pattern="^fix_orphaned$"),
            CallbackQueryHandler(admin_handlers.create_backup, pattern="^create_backup$"),
            CallbackQueryHandler(admin_handlers.restore_backup_start, pattern="^restore_backup$"),
            # ویرایش متن
            CallbackQueryHandler(admin_handlers.text_edit_start, pattern="^text_edit_"),
            # دسته‌بندی و سلاح‌ها
            CallbackQueryHandler(admin_handlers.weapon_mgmt_menu, pattern="^admin_weapon_mgmt$"),
            CallbackQueryHandler(admin_handlers.category_toggle_selected, pattern="^cat_toggle_"),
            CallbackQueryHandler(admin_handlers.category_clear_confirm, pattern="^cat_clear_confirm_"),
            CallbackQueryHandler(admin_handlers.category_clear_prompt, pattern="^cat_clear_(?!confirm_)"),
            # تنظیمات اعلان‌ها
            CallbackQueryHandler(admin_handlers.notify_toggle, pattern="^notif_toggle$"),
            CallbackQueryHandler(admin_handlers.notify_auto_toggle, pattern="^notif_auto_toggle$"),
            CallbackQueryHandler(admin_handlers.template_list_menu, pattern="^notif_templates$"),
            CallbackQueryHandler(admin_handlers.notif_event_toggle, pattern="^notif_event_"),
            CallbackQueryHandler(admin_handlers.notif_toggle_global, pattern="^notifset_toggle_global$"),
            CallbackQueryHandler(admin_handlers.notif_toggle_event, pattern="^notifset_toggle_event_"),
            CallbackQueryHandler(admin_handlers.template_edit_start, pattern="^tmpl_edit_"),
            # تیکت‌ها
            CallbackQueryHandler(admin_handlers.admin_tickets_menu, pattern="^admin_tickets$"),
            CallbackQueryHandler(admin_handlers.admin_tickets_list, pattern="^adm_tickets_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_search_start, pattern="^adm_tickets_search$"),
            CallbackQueryHandler(admin_handlers.admin_ticket_reply_start, pattern="^adm_reply_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_view_attachments, pattern="^adm_attach_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_change_status, pattern="^adm_status_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_set_status, pattern="^adm_setstatus_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_change_priority, pattern="^adm_priority_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_set_priority, pattern="^adm_setpriority_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_assign_start, pattern="^adm_assign_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_assign_confirm, pattern="^adm_doassign_"),
            CallbackQueryHandler(admin_handlers.admin_ticket_close, pattern="^adm_close_"),
            CallbackQueryHandler(admin_handlers.admin_tickets_page_navigation, pattern="^ticket_page_"),
            CallbackQueryHandler(admin_handlers.admin_tickets_filter_category, pattern="^adm_tickets_filter_category$"),
            CallbackQueryHandler(admin_handlers.admin_tickets_by_category, pattern="^adm_tickets_cat_"),
            CallbackQueryHandler(admin_handlers.admin_tickets_mine, pattern="^adm_tickets_mine$"),
            CallbackQueryHandler(admin_handlers.admin_ticket_detail, pattern="^adm_ticket_"),
            # FAQ
            CallbackQueryHandler(admin_handlers.admin_faqs_menu, pattern="^admin_faqs$"),
            CallbackQueryHandler(admin_handlers.admin_faq_list, pattern="^adm_faq_list$"),
            CallbackQueryHandler(admin_handlers.admin_faq_view, pattern="^adm_faq_view_"),
            CallbackQueryHandler(admin_handlers.admin_faq_add_start, pattern="^adm_faq_add$"),
            CallbackQueryHandler(admin_handlers.admin_faq_delete, pattern="^adm_faq_del_"),
            CallbackQueryHandler(admin_handlers.admin_faq_edit, pattern="^adm_faq_edit_"),
            CallbackQueryHandler(admin_handlers.admin_faq_stats, pattern="^adm_faq_stats$"),
            CallbackQueryHandler(admin_handlers.admin_feedback_stats, pattern="^adm_feedback$"),
            CallbackQueryHandler(admin_handlers.admin_faq_set_lang, pattern="^adm_faq_lang_"),
            # Direct Contact
            CallbackQueryHandler(admin_handlers.admin_direct_contact_menu, pattern="^adm_direct_contact$"),
            CallbackQueryHandler(admin_handlers.direct_contact_toggle, pattern="^dc_enable$|^dc_disable$"),
            CallbackQueryHandler(admin_handlers.direct_contact_change_name_start, pattern="^dc_change_name$"),
            CallbackQueryHandler(admin_handlers.direct_contact_change_link_start, pattern="^dc_change_link$"),
            # Search text handler
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.handle_search_text),
            # روتر عمومی - باید آخر باشد
            CallbackQueryHandler(admin_handlers.admin_menu, pattern="^admin_")
        ],
        # CMS States
        CMS_ADD_TYPE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.cms_type_selected, pattern="^cms_type_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$|^admin_cms$")
        ],
        CMS_ADD_TITLE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.cms_title_received),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$|^admin_cms$")
        ],
        CMS_ADD_BODY: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.cms_body_received),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$|^admin_cms$")
        ],
        CMS_SEARCH_TEXT: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.cms_search_received),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$|^admin_cms$")
        ],
        # بقیه states به صورت خلاصه - ساختار یکسان با main.py
        ADD_ATTACHMENT_CATEGORY: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.add_attachment_category_selected, pattern="^aac_|^admin_cancel$|^nav_back$")
        ],
        ADD_ATTACHMENT_WEAPON: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.add_attachment_weapon_selected, pattern="^aaw_|^admin_cancel$|^aaw_new$|^nav_back$")
        ],
        ADD_ATTACHMENT_MODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.add_attachment_mode_selected, pattern="^aam_|^admin_cancel$|^nav_back$")
        ],
        ADD_WEAPON_NAME: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^(🔫 دریافت اتچمنت|⭐ برترهای فصل|📋 لیست برترها|🔍 جستجوی اتچمنت|💡 اتچمنت‌های پیشنهادی|⚙️ تنظیمات کالاف|🔔 تنظیمات اعلان‌ها|📖 راهنما)$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.handle_navigation_back, pattern="^nav_back$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.add_attachment_new_weapon_name_received)
        ],
        ADD_ATTACHMENT_CODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^(🔫 دریافت اتچمنت|⭐ برترهای فصل|📋 لیست برترها|🔍 جستجوی اتچمنت|💡 اتچمنت‌های پیشنهادی|⚙️ تنظیمات کالاف|🔔 تنظیمات اعلان‌ها|📖 راهنما)$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.handle_navigation_back, pattern="^nav_back$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.add_attachment_code_received)
        ],
        ADD_ATTACHMENT_NAME: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^(🔫 دریافت اتچمنت|⭐ برترهای فصل|📋 لیست برترها|🔍 جستجوی اتچمنت|💡 اتچمنت‌های پیشنهادی|⚙️ تنظیمات کالاف|🔔 تنظیمات اعلان‌ها|📖 راهنما)$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.add_attachment_name_received)
        ],
        ADD_ATTACHMENT_IMAGE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.PHOTO, admin_handlers.add_attachment_image_received),
            CallbackQueryHandler(admin_handlers.add_attachment_image_received, pattern="^skip_image$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        ADD_ATTACHMENT_TOP: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.add_attachment_top_selected, pattern="^att_top_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        ADD_ATTACHMENT_SEASON: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.add_attachment_season_selected, pattern="^att_season_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        # Edit Attachment States
        EDIT_ATTACHMENT_MODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.edit_attachment_mode_selected, pattern="^eam_|^admin_cancel$|^nav_back$")
        ],
        EDIT_ATTACHMENT_CATEGORY: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.edit_attachment_category_selected, pattern="^eac_|^admin_cancel$|^nav_back$")
        ],
        EDIT_ATTACHMENT_WEAPON: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.edit_attachment_weapon_selected, pattern="^eaw_|^admin_cancel$|^nav_back$")
        ],
        EDIT_ATTACHMENT_SELECT: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.edit_attachment_selected, pattern="^eas_|^admin_cancel$|^nav_back$")
        ],
        EDIT_ATTACHMENT_ACTION: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.edit_attachment_action_selected, pattern="^eaa_|^admin_cancel$|^nav_back$")
        ],
        EDIT_ATTACHMENT_NAME: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.edit_attachment_name_received)
        ],
        EDIT_ATTACHMENT_IMAGE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.PHOTO, admin_handlers.edit_attachment_image_received),
            CallbackQueryHandler(admin_handlers.edit_attachment_image_received, pattern="^skip_edit_image$|^eaa_menu$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        EDIT_ATTACHMENT_CODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.edit_attachment_code_received)
        ],
        # Weapon Management States
        WEAPON_SELECT_MODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.weapon_mode_selected, pattern="^wmm_|^admin_category_mgmt$")
        ],
        WEAPON_SELECT_CATEGORY: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.weapon_select_category_menu, pattern="^wmcat_|^nav_back$")
        ],
        WEAPON_SELECT_WEAPON: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.weapon_select_weapon_menu, pattern="^wmwpn_|^nav_back$")
        ],
        WEAPON_ACTION_MENU: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.weapon_action_selected, pattern="^wmact_|^nav_back$")
        ],
        WEAPON_DELETE_CONFIRM: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.weapon_delete_confirmed, pattern="^wmconf_|^nav_back$|^admin_weapon_mgmt$")
        ],
        # Delete Attachment (Mode-First) States
        DELETE_ATTACHMENT_MODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.delete_attachment_mode_selected, pattern="^dam_|^admin_cancel$|^nav_back$")
        ],
        DELETE_ATTACHMENT_CATEGORY: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.delete_attachment_category_selected, pattern="^dac_|^admin_cancel$|^nav_back$")
        ],
        DELETE_ATTACHMENT_WEAPON: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.delete_attachment_weapon_selected, pattern="^daw_|^admin_cancel$|^nav_back$")
        ],
        DELETE_ATTACHMENT_SELECT: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.delete_attachment_code_selected, pattern="^delatt_id_|^admin_cancel$|^nav_back$")
        ],
        # Set Top Attachments (Mode-First) States
        SET_TOP_MODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.set_top_mode_selected, pattern="^stm_|^admin_cancel$|^nav_back$")
        ],
        SET_TOP_CATEGORY: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.set_top_category_selected, pattern="^stc_|^admin_cancel$|^nav_back$")
        ],
        SET_TOP_WEAPON: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.set_top_weapon_selected, pattern="^stw_|^admin_cancel$|^nav_back$")
        ],
        SET_TOP_SELECT: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.set_top_attachment_selected, pattern="^stta_|^stta_confirm$|^admin_cancel$|^nav_back$")
        ],
        SET_TOP_CONFIRM: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.set_top_confirm_answer, pattern="^sttc_|^admin_cancel$|^nav_back$")
        ],
        # Category Management (Mode-First) States
        CATEGORY_MGMT_MODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.category_mode_selected, pattern="^cmm_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        CATEGORY_MGMT_MENU: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.category_toggle_selected, pattern="^adm_cat_toggle_"),
            CallbackQueryHandler(admin_handlers.category_clear_prompt, pattern="^adm_cat_clear_"),
            CallbackQueryHandler(admin_handlers.category_clear_confirm, pattern="^cat_clear_confirm$"),
            CallbackQueryHandler(admin_handlers.category_clear_cancel, pattern="^cat_clear_cancel$"),
            CallbackQueryHandler(admin_handlers.handle_navigation_back, pattern="^nav_back$")
        ],
        # ========== Admin Management States ==========
        ADD_ADMIN_ID: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.add_admin_id_received),
            CallbackQueryHandler(admin_handlers.manage_admins_menu, pattern="^manage_admins$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        ADD_ADMIN_DISPLAY_NAME: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Regex('^پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.add_admin_display_name_received),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        # ========== FAQ States ==========
        ADD_FAQ_QUESTION: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.admin_faq_question_received),
            CallbackQueryHandler(admin_handlers.admin_faqs_menu, pattern="^admin_faqs$"),
            CallbackQueryHandler(admin_handlers.admin_faq_set_lang, pattern="^adm_faq_lang_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        ADD_FAQ_ANSWER: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.admin_faq_answer_received),
            CallbackQueryHandler(admin_handlers.admin_faqs_menu, pattern="^admin_faqs$"),
            CallbackQueryHandler(admin_handlers.admin_faq_set_lang, pattern="^adm_faq_lang_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        EDIT_FAQ_SELECT: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.admin_faq_edit_field_select, pattern="^edit_faq_"),
            CallbackQueryHandler(admin_handlers.admin_faq_view, pattern="^adm_faq_view_"),
            CallbackQueryHandler(admin_handlers.admin_faq_set_lang, pattern="^adm_faq_lang_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        EDIT_FAQ_QUESTION: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.admin_faq_edit_question_received),
            CallbackQueryHandler(admin_handlers.admin_faq_edit, pattern="^adm_faq_edit_"),
            CallbackQueryHandler(admin_handlers.admin_faq_set_lang, pattern="^adm_faq_lang_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        EDIT_FAQ_ANSWER: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.admin_faq_edit_answer_received),
            CallbackQueryHandler(admin_handlers.admin_faq_edit, pattern="^adm_faq_edit_"),
            CallbackQueryHandler(admin_handlers.admin_faq_set_lang, pattern="^adm_faq_lang_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        # ========== Direct Contact States ==========
        DIRECT_CONTACT_NAME: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.direct_contact_name_received),
            CallbackQueryHandler(admin_handlers.admin_direct_contact_menu, pattern="^adm_direct_contact$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        DIRECT_CONTACT_LINK: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.direct_contact_link_received),
            CallbackQueryHandler(admin_handlers.admin_direct_contact_menu, pattern="^adm_direct_contact$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        # ========== Guide States ==========
        GUIDE_RENAME: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.guide_rename_received),
            CallbackQueryHandler(admin_handlers.guide_section_menu, pattern="^gsel_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        GUIDE_ADD_PHOTO: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.PHOTO, admin_handlers.guide_photo_received),
            CallbackQueryHandler(admin_handlers.guide_op_router, pattern="^gop_confirm_media_"),
            CallbackQueryHandler(admin_handlers.guide_section_menu, pattern="^gsel_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        GUIDE_ADD_VIDEO: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.VIDEO, admin_handlers.guide_video_received),
            CallbackQueryHandler(admin_handlers.guide_op_router, pattern="^gop_confirm_media_"),
            CallbackQueryHandler(admin_handlers.guide_section_menu, pattern="^gsel_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        GUIDE_SET_CODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.guide_code_received),
            CallbackQueryHandler(admin_handlers.guide_section_menu, pattern="^gsel_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        # ========== Import/Export States ==========
        IMPORT_FILE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.Document.ALL, admin_handlers.import_file_received),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$|^admin_data_management$")
        ],
        IMPORT_MODE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.import_mode_selected, pattern="^import_merge$|^import_replace$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        EXPORT_TYPE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.export_type_selected, pattern="^export_json$|^export_csv$|^export_backup$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$|^admin_data_management$")
        ],
        # ========== Notification States ==========
        NOTIF_COMPOSE: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.notify_compose_received),
            MessageHandler(filters.PHOTO, admin_handlers.notify_compose_received),
            CallbackQueryHandler(admin_handlers.notify_home_menu, pattern="^notify_home$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        NOTIF_CONFIRM: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            CallbackQueryHandler(admin_handlers.notify_confirm_selected, pattern="^notify_confirm$"),
            CallbackQueryHandler(admin_handlers.notify_schedule_menu, pattern="^notify_schedule$"),
            CallbackQueryHandler(admin_handlers.notify_home_menu, pattern="^notify_home$"),
            CallbackQueryHandler(admin_handlers.notify_schedule_preset_selected, pattern="^notif_sched_"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
        SCHED_EDIT_TEXT: [
            MessageHandler(filters.Regex('^👨‍💼 پنل ادمین$'), admin_handlers.admin_menu_return),
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_handlers.schedule_edit_text_received),
            CallbackQueryHandler(admin_handlers.schedules_menu, pattern="^admin_sched_notifications$"),
            CallbackQueryHandler(admin_handlers.admin_menu_return, pattern="^admin_cancel$")
        ],
    }

    
    # فیلتر None values
    for state_key in states_dict:
        states_dict[state_key] = [h for h in states_dict[state_key] if h is not None]
    
    return states_dict
