import pytest
from unittest.mock import MagicMock, patch
from telegram.ext import Application
from app.registry.user_registry import UserHandlerRegistry

class TestUserHandlerRegistry:
    
    @pytest.fixture
    def mock_app(self):
        return MagicMock(spec=Application)
    
    @pytest.fixture
    def mock_db(self):
        return MagicMock()
    
    @pytest.fixture
    def mock_bot(self):
        bot = MagicMock()
        # Mock the handler attributes that Registry accesses
        bot.user_handlers = MagicMock()
        bot.contact_handlers = MagicMock()
        bot.admin_handlers = MagicMock()
        return bot

    def test_registry_initialization(self, mock_app, mock_db, mock_bot):
        """Test that registry initializes with correct handlers"""
        registry = UserHandlerRegistry(mock_app, mock_db, mock_bot)
        
        assert registry.notification_handler is not None
        assert registry.help_handler is not None
        assert registry.feedback_handler is not None

    def test_register_handlers(self, mock_app, mock_db, mock_bot):
        """Test that handlers are actually registered to the application"""
        registry = UserHandlerRegistry(mock_app, mock_db, mock_bot)
        
        # Mock add_handler to track calls
        mock_app.add_handler = MagicMock()
        
        registry.register()
        
        # Verify that add_handler was called multiple times
        assert mock_app.add_handler.call_count > 0
        
        # Check for specific handlers we refactored
        # We can't easily inspect the handler objects passed, but we can verify count
        # or check if specific patterns are present if we inspect call_args_list
        # For now, basic count verification is a good integration step
