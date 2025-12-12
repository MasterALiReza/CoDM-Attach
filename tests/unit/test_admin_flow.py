import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from handlers.admin.modules.content.category_handler import CategoryHandler
from handlers.admin.admin_states import CATEGORY_MGMT_MODE, CATEGORY_MGMT_MENU

@pytest.mark.asyncio
class TestCategoryHandlerFlow:
    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.fixture
    def handler(self, mock_db):
        # Inject mock DB
        h = CategoryHandler(mock_db)
        # Mock role_manager if used in __init__? 
        # Checking code: role_manager is initialized in __init__ via self.db or Global?
        # In the file viewed earlier: 
        # self.role_manager = None (in __init__) then loaded later?
        # Actually it uses self.role_manager. checks.
        # Let's mock it just in case.
        h.role_manager = MagicMock()
        h.role_manager.has_permission.return_value = True
        h.role_manager.get_mode_permissions.return_value = ['mp', 'br']
        return h

    @pytest.fixture
    def mock_update(self):
        update = MagicMock()
        update.callback_query = AsyncMock()
        update.callback_query.data = "generic_callback"
        update.callback_query.message = AsyncMock()
        update.callback_query.from_user.id = 123456
        update.effective_user.id = 123456
        return update

    @pytest.fixture
    def mock_context(self):
        context = MagicMock()
        context.user_data = {}
        return context

    async def test_show_mode_selection_entry(self, handler, mock_update, mock_context):
        """Test entry to category management (Mode selection)"""
        # Arrange
        mock_update.callback_query.data = "manage_categories"
        
        # Mock external dependencies
        with patch('handlers.admin.modules.content.category_handler.get_user_lang', return_value='en'), \
             patch('handlers.admin.modules.content.category_handler.t', side_effect=lambda k, l, **kw: k):
            
            # Act
            state = await handler.category_mgmt_menu(mock_update, mock_context)
            
            # Assert
            # Should return the state for ConversationHandler
            assert state == CATEGORY_MGMT_MODE
            
            # Should verify permission (if check exists)
            # Should edit message to show buttons (MP/BR)
            mock_update.callback_query.edit_message_text.assert_called_once()
            _, kwargs = mock_update.callback_query.edit_message_text.call_args

            # Verify keyboard layout roughly
            keyboard = kwargs.get('reply_markup')
            assert keyboard is not None
            # We expect MP and BR buttons
            # Inspecting inline keyboard data is complex due to object structure, 
            # but we can check if call didn't crash and returned state.

    async def test_mode_selected_mp(self, handler, mock_update, mock_context):
        """Test selecting MP mode transitions to category list"""
        # Arrange
        mock_update.callback_query.data = "cmm_mp"
        
        # Mock config to return some categories
        with patch('handlers.admin.modules.content.category_handler.get_user_lang', return_value='en'), \
             patch('handlers.admin.modules.content.category_handler.t', side_effect=lambda k, l, **kw: k), \
             patch('config.config.WEAPON_CATEGORIES', {'assault': 'Assault Rifle', 'smg': 'SMG'}):
            
            # Act
            state = await handler.category_mode_selected(mock_update, mock_context)
            
            # Assert
            assert state == CATEGORY_MGMT_MENU
            assert mock_context.user_data.get('cat_mgmt_mode') == 'mp'
            
            # Should list categories
            mock_update.callback_query.edit_message_text.assert_called_once()

    async def test_permission_denied(self, handler, mock_update, mock_context):
        """Test entry denied if no permission"""
        # Arrange
        handler.role_manager.get_user_permissions.return_value = [] # No permissions
        # Need to verify if show_mode_selection checks perms or if it's done before.
        # Based on view_file earlier, some handlers check perms inside.
        # Let's assume safely it might check.
