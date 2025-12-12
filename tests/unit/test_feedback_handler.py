"""
Unit Tests for Feedback Handler
Tests for user voting and feedback functionality
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from handlers.user.modules.feedback.feedback_handler import FeedbackHandler


@pytest.fixture
def mock_db():
    """Mock database adapter"""
    db = MagicMock()
    db.get_attachment.return_value = {'id': 1, 'name': 'Test', 'like_count': 0, 'dislike_count': 0}
    db.add_vote.return_value = {'success': True, 'like_count': 1, 'dislike_count': 0}
    db.add_feedback.return_value = True
    return db


@pytest.fixture
def mock_update():
    """Mock Telegram Update"""
    update = MagicMock()
    update.callback_query = AsyncMock()
    update.callback_query.data = "vote_like_1"
    update.callback_query.from_user.id = 123456
    update.effective_user.id = 123456
    update.message = AsyncMock()
    update.message.text = "Great attachment!"
    return update


@pytest.fixture
def mock_context():
    """Mock Telegram Context"""
    context = MagicMock()
    context.user_data = {}
    context.bot = AsyncMock()
    return context


@pytest.mark.asyncio
class TestFeedbackHandler:

    @pytest.fixture
    def handler(self, mock_db):
        h = FeedbackHandler(mock_db)
        return h

    async def test_handler_has_all_methods(self, handler):
        """Test handler has all required methods"""
        assert hasattr(handler, 'handle_vote_like')
        assert hasattr(handler, 'handle_vote_dislike')
        assert hasattr(handler, 'handle_feedback_request')
        assert hasattr(handler, 'handle_feedback_text')
        assert hasattr(handler, 'handle_feedback_cancel')
        assert hasattr(handler, 'handle_copy_code')
        assert hasattr(handler, 'build_feedback_buttons')

    async def test_rate_limit_method_exists(self, handler):
        """Test rate limiting method exists"""
        assert hasattr(handler, '_check_rate_limit')

    async def test_update_buttons_method_exists(self, handler):
        """Test button update method exists"""
        assert hasattr(handler, '_update_feedback_buttons')

    async def test_cooldown_constants(self, handler):
        """Test cooldown constants are defined"""
        assert hasattr(handler, 'VOTE_COOLDOWN_SECONDS')
        assert isinstance(handler.VOTE_COOLDOWN_SECONDS, (int, float))

    async def test_vote_cooldown_tracking(self, handler):
        """Test vote cooldown dictionary exists"""
        assert hasattr(handler, '_vote_cooldown')
        assert isinstance(handler._vote_cooldown, dict)

    async def test_build_feedback_buttons_returns_list(self, handler):
        """Test build_feedback_buttons returns proper structure"""
        buttons = handler.build_feedback_buttons(
            attachment_id=1,
            like_count=5,
            dislike_count=2,
            lang='en'
        )
        assert isinstance(buttons, list)
