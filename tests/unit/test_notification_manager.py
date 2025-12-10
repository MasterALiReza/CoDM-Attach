import pytest
from unittest.mock import MagicMock, patch
from managers.notification_manager import NotificationManager

class TestNotificationManager:
    
    @pytest.fixture
    def mock_db(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_subs(self):
        return MagicMock()
    
    @pytest.fixture
    def manager(self, mock_db, mock_subs):
        return NotificationManager(mock_db, mock_subs)

    def test_toggle_user_notifications(self, manager, mock_db):
        """Test toggling global notification status"""
        user_id = 12345
        
        # Mock existing preferences
        mock_db.get_user_notification_preferences.return_value = {'enabled': True}
        mock_db.update_user_notification_preferences.return_value = True
        
        # Toggle off
        result = manager.toggle_user_notifications(user_id)
        assert result is True
        
        # Verify DB update
        mock_db.update_user_notification_preferences.assert_called_once()
        args = mock_db.update_user_notification_preferences.call_args[0]
        assert args[0] == user_id
        assert args[1]['enabled'] is False
        
    @pytest.mark.asyncio
    async def test_get_active_users_optimized(self, manager, mock_db):
        """Test that the optimized DB method is called"""
        # Mock the optimized method existence
        mock_db.get_users_for_notification = MagicMock(return_value={1, 2, 3})
        
        users = await manager._get_active_users_for_events(
            ['add_attachment'],
            'mp'
        )
        
        assert users == {1, 2, 3}
        mock_db.get_users_for_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_fallback_logic(self, manager, mock_db, mock_subs):
        """Test fallback to Python filtering if optimized method missing"""
        # Remove optimized method
        del mock_db.get_users_for_notification
        
        # Setup subscribers and preferences
        mock_subs.all.return_value = {1, 2}
        
        # User 1: enabled, mp, add_attachment
        # User 2: disabled
        def get_prefs(user_id):
            if user_id == 1:
                return {'enabled': True, 'modes': ['mp'], 'events': {'add_attachment': True}}
            return {'enabled': False}
            
        # Mock get_user_notification_preferences on db instead of manager.get_user_preferences
        # because _get_active_users_for_events_legacy calls self.db.get_user_notification_preferences
        mock_db.get_user_notification_preferences.side_effect = get_prefs
        
        users = await manager._get_active_users_for_events(['add_attachment'], 'mp')
        
        assert 1 in users
        assert 2 not in users
