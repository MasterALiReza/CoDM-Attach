import random
import pytest

from utils.subscribers_pg import SubscribersPostgres

pytestmark = pytest.mark.integration


def test_subscribers_add_remove_all_is_subscribed(db_adapter):
    sp = SubscribersPostgres(db_adapter=db_adapter)
    user_id = 800000000 + random.randint(0, 99999)

    # ensure clean state
    try:
        sp.remove(user_id)
    except Exception:
        pass

    # add
    added = sp.add(user_id)
    assert added is True or added is False  # True if new, False if already active

    # is_subscribed
    assert sp.is_subscribed(user_id) is True

    # all contains
    all_ids = sp.all()
    assert isinstance(all_ids, list)
    assert user_id in all_ids

    # remove -> unsubscribes (soft delete)
    removed = sp.remove(user_id)
    assert removed is True or removed is False

    assert sp.is_subscribed(user_id) is False
