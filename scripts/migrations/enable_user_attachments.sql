-- Enable User Attachment System
-- This script explicitly sets the 'system_enabled' setting to '1' (true) in user_attachment_settings table.
-- This ensures the "User Attachments" button is visible in the main menu.

INSERT INTO user_attachment_settings (setting_key, setting_value, updated_at)
VALUES ('system_enabled', '1', NOW())
ON CONFLICT (setting_key) 
DO UPDATE SET setting_value = '1', updated_at = NOW();
