import random
import time
import pytest

pytestmark = pytest.mark.integration


def test_user_submission_stats_update_flow(db_adapter):
    user_id = 900000000 + random.randint(0, 99999)

    # Ensure user exists
    assert db_adapter.upsert_user(user_id, username="test_user", first_name="Tester") is True

    # Initial fetch should create defaults (and row if absent)
    stats = db_adapter.get_user_submission_stats(user_id)
    assert stats is not None
    assert stats.get("total_submissions", 0) == 0
    assert stats.get("daily_submissions", 0) == 0
    assert stats.get("violation_count", 0) == 0
    assert float(stats.get("strike_count", 0.0)) == 0.0

    # Update: increment total/daily + add violation/strike
    ok = db_adapter.update_submission_stats(
        user_id,
        increment_total=True,
        increment_daily=True,
        add_violation=1,
        add_strike=0.5,
    )
    assert ok is True

    stats2 = db_adapter.get_user_submission_stats(user_id)
    assert stats2["total_submissions"] >= 1
    assert stats2["daily_submissions"] >= 1
    assert stats2["violation_count"] >= 1
    assert float(stats2["strike_count"]) >= 0.5
    assert stats2["last_submission_at"] is not None

    # Ban and unban flow
    assert db_adapter.ban_user_from_submissions(user_id, reason="test") is True
    stats3 = db_adapter.get_user_submission_stats(user_id)
    assert bool(stats3.get("is_banned")) is True

    assert db_adapter.unban_user_from_submissions(user_id) is True
    stats4 = db_adapter.get_user_submission_stats(user_id)
    assert bool(stats4.get("is_banned")) is False
    # strike_count reset path
    assert float(stats4.get("strike_count", 0.0)) == 0.0
