"""
Unit Tests for Admin System Handlers
Tests for AdminManagementHandler, NotificationHandler, ImportExportHandler
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from handlers.admin.modules.system.admin_management import AdminManagementHandler
from handlers.admin.admin_states import ADMIN_MENU


@pytest.fixture
def mock_db():
    """Mock database adapter"""
    db = MagicMock()
    db.get_all_admins.return_value = []
    db.add_admin.return_value = True
    db.remove_admin.return_value = True
    return db


@pytest.fixture
def mock_update():
    """Mock Telegram Update"""
    update = MagicMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "admin_mgmt_menu"
    update.callback_query.from_user.id = 123456
    update.effective_user.id = 123456
    update.message = MagicMock()
    update.message.text = "test"
    return update


@pytest.fixture
def mock_context():
    """Mock Telegram Context"""
    context = MagicMock()
    context.user_data = {}
    context.bot = AsyncMock()
    return context


# ==================== AdminManagementHandler Tests ====================

@pytest.mark.asyncio
class TestAdminManagementHandler:

    @pytest.fixture
    def handler(self, mock_db):
        h = AdminManagementHandler(mock_db)
        h.role_manager = MagicMock()
        h.role_manager.is_super_admin.return_value = True
        h.role_manager.get_all_roles.return_value = ['content_manager', 'support_agent']
        return h

    async def test_handler_has_all_methods(self, handler):
        """Test handler has all required methods"""
        assert hasattr(handler, 'manage_admins_menu')
        assert hasattr(handler, 'add_admin_start')
        assert hasattr(handler, 'add_admin_role_selected')
        assert hasattr(handler, 'add_admin_id_received')
        assert hasattr(handler, 'add_admin_display_name_received')
        assert hasattr(handler, 'view_roles_menu')
        assert hasattr(handler, 'edit_admin_role_start')
        assert hasattr(handler, 'edit_admin_role_select')
        assert hasattr(handler, 'add_role_to_admin')
        assert hasattr(handler, 'add_role_confirm')
        assert hasattr(handler, 'delete_role_from_admin')
        assert hasattr(handler, 'delete_role_confirm')
        assert hasattr(handler, 'remove_admin_start')
        assert hasattr(handler, 'remove_admin_confirmed')

    async def test_cache_methods_exist(self, handler):
        """Test cache management methods exist"""
        assert hasattr(handler, '_get_cached_admin_list')
        assert hasattr(handler, '_invalidate_admin_cache')

    async def test_set_role_manager(self, handler):
        """Test role manager can be set"""
        new_rm = MagicMock()
        handler.set_role_manager(new_rm)
        assert handler.role_manager == new_rm

    async def test_cache_invalidation(self, handler):
        """Test cache invalidation works"""
        handler._admin_list_cache = [{'id': 1}]
        handler._invalidate_admin_cache()
        assert handler._admin_list_cache is None or len(handler._admin_list_cache) == 0


# ==================== NotificationHandler Tests ====================

@pytest.mark.asyncio
class TestNotificationHandler:

    async def test_module_imports(self):
        """Test notification handler is importable"""
        from handlers.admin.modules.system.notification_handler import NotificationHandler
        assert NotificationHandler is not None

    async def test_handler_has_methods(self):
        """Test handler has notification methods"""
        from handlers.admin.modules.system.notification_handler import NotificationHandler
        handler = NotificationHandler(MagicMock())
        
        # Core notification methods
        assert hasattr(handler, 'notify_start')
        assert hasattr(handler, 'notify_home_menu')
        assert hasattr(handler, 'notify_compose_start')


# ==================== ImportExportHandler Tests ====================

@pytest.mark.asyncio
class TestImportExportHandler:

    async def test_module_imports(self):
        """Test import/export handler is importable"""
        from handlers.admin.modules.system.import_export import ImportExportHandler
        assert ImportExportHandler is not None

    async def test_handler_has_methods(self):
        """Test handler has import/export methods"""
        from handlers.admin.modules.system.import_export import ImportExportHandler
        handler = ImportExportHandler(MagicMock())
        
        assert hasattr(handler, 'export_start')
        assert hasattr(handler, 'import_start')
        assert hasattr(handler, 'export_type_selected')
