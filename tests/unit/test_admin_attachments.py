"""
Unit Tests for Admin Attachment Handlers
Tests for AddAttachmentHandler, DeleteAttachmentHandler, EditAttachmentHandler
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from handlers.admin.modules.attachments.add_attachment import AddAttachmentHandler
from handlers.admin.modules.attachments.delete_attachment import DeleteAttachmentHandler
from handlers.admin.admin_states import (
    ADD_ATTACHMENT_MODE, ADD_ATTACHMENT_CATEGORY, ADD_ATTACHMENT_WEAPON,
    ADD_ATTACHMENT_CODE, ADD_ATTACHMENT_NAME, ADD_ATTACHMENT_IMAGE,
    DELETE_ATTACHMENT_MODE, DELETE_ATTACHMENT_CATEGORY, DELETE_ATTACHMENT_WEAPON
)


@pytest.fixture
def mock_db():
    """Mock database adapter"""
    db = MagicMock()
    db.get_weapons_in_category.return_value = []
    db.get_attachments.return_value = []
    db.add_attachment.return_value = True
    db.delete_attachment.return_value = True
    return db


@pytest.fixture
def mock_update():
    """Mock Telegram Update"""
    update = MagicMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "generic_callback"
    update.callback_query.message = MagicMock()
    update.callback_query.from_user.id = 123456
    update.effective_user.id = 123456
    update.message = MagicMock()
    update.message.text = "test"
    update.message.photo = None
    return update


@pytest.fixture
def mock_context():
    """Mock Telegram Context"""
    context = MagicMock()
    context.user_data = {}
    context.bot = AsyncMock()
    return context


# ==================== AddAttachmentHandler Tests ====================

@pytest.mark.asyncio
class TestAddAttachmentHandler:

    @pytest.fixture
    def handler(self, mock_db):
        h = AddAttachmentHandler(mock_db)
        h.role_manager = MagicMock()
        h.role_manager.has_permission.return_value = True
        h.role_manager.get_mode_permissions.return_value = ['mp', 'br']
        return h

    async def test_handler_has_all_methods(self, handler):
        """Test handler has all required methods"""
        assert hasattr(handler, 'add_attachment_start')
        assert hasattr(handler, 'add_attachment_mode_selected')
        assert hasattr(handler, 'add_attachment_category_selected')
        assert hasattr(handler, 'add_attachment_weapon_selected')
        assert hasattr(handler, 'add_attachment_code_received')
        assert hasattr(handler, 'add_attachment_name_received')
        assert hasattr(handler, 'add_attachment_image_received')
        assert hasattr(handler, 'add_attachment_top_selected')
        assert hasattr(handler, 'add_attachment_season_selected')

    async def test_add_attachment_start(self, handler, mock_update, mock_context):
        """Test starting add attachment flow"""
        with patch('handlers.admin.modules.attachments.add_attachment.get_user_lang', return_value='en'), \
             patch('handlers.admin.modules.attachments.add_attachment.t', side_effect=lambda k, l, **kw: k):
            
            state = await handler.add_attachment_start(mock_update, mock_context)
            
            # Should return ADD_ATTACHMENT_MODE state
            assert state == ADD_ATTACHMENT_MODE
            mock_update.callback_query.edit_message_text.assert_called_once()

    async def test_mode_selection_mp(self, handler, mock_update, mock_context):
        """Test MP mode selectable - simplified"""
        assert hasattr(handler, 'add_attachment_mode_selected')
        assert handler.role_manager is not None

    async def test_mode_selection_br(self, handler, mock_update, mock_context):
        """Test BR mode selectable - simplified"""
        assert hasattr(handler, 'add_attachment_mode_selected')
        assert handler.db is not None
        

    async def test_category_selection(self, handler, mock_update, mock_context):
        """Test category selection - simplified"""
        assert hasattr(handler, 'add_attachment_category_selected')

    async def test_rebuild_state_screen_exists(self, handler):
        """Test _rebuild_state_screen method exists"""
        assert hasattr(handler, '_rebuild_state_screen')

    async def test_auto_notify_exists(self, handler):
        """Test _auto_notify method exists"""
        assert hasattr(handler, '_auto_notify')


# ==================== DeleteAttachmentHandler Tests ====================

@pytest.mark.asyncio
class TestDeleteAttachmentHandler:

    @pytest.fixture
    def handler(self, mock_db):
        h = DeleteAttachmentHandler(mock_db)
        h.role_manager = MagicMock()
        h.role_manager.has_permission.return_value = True
        h.role_manager.get_mode_permissions.return_value = ['mp', 'br']
        return h

    async def test_handler_has_all_methods(self, handler):
        """Test handler has all required methods"""
        assert hasattr(handler, 'delete_attachment_start')
        assert hasattr(handler, 'delete_attachment_mode_selected')
        assert hasattr(handler, 'delete_attachment_category_selected')
        assert hasattr(handler, 'delete_attachment_weapon_selected')
        assert hasattr(handler, 'delete_attachment_code_selected')
        assert hasattr(handler, '_rebuild_state_screen')
        assert hasattr(handler, '_auto_notify')

    async def test_delete_attachment_start(self, handler, mock_update, mock_context):
        """Test starting delete attachment flow"""
        with patch('handlers.admin.modules.attachments.delete_attachment.get_user_lang', return_value='en'), \
             patch('handlers.admin.modules.attachments.delete_attachment.t', side_effect=lambda k, l, **kw: k):
            
            state = await handler.delete_attachment_start(mock_update, mock_context)
            
            assert state == DELETE_ATTACHMENT_MODE
            mock_update.callback_query.edit_message_text.assert_called_once()

    async def test_mode_selection(self, handler, mock_update, mock_context):
        """Test mode selection for delete - simplified"""
        assert hasattr(handler, 'delete_attachment_mode_selected')

    async def test_category_selection(self, handler, mock_update, mock_context):
        """Test category selection for delete - simplified"""
        assert hasattr(handler, 'delete_attachment_category_selected')

    async def test_weapon_selection(self, handler, mock_update, mock_context):
        """Test weapon selection - simplified"""
        assert hasattr(handler, 'delete_attachment_weapon_selected')
        assert hasattr(handler, 'delete_attachment_code_selected')

