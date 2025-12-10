import pytest

pytestmark = pytest.mark.integration


def _find_in_results(results, code: str) -> bool:
    for item in results:
        att = (item or {}).get("attachment", {})
        if att.get("code") == code:
            return True
    return False


def test_fts_search_returns_inserted(db_adapter):
    category = "assault_rifle"
    weapon = "M4"
    code = "M4C1"
    name = "Tactical Grip"

    # Ensure weapon exists
    assert db_adapter.add_weapon(category, weapon) is True
    # Add attachment (mp)
    ok = db_adapter.add_attachment(category, weapon, code, name, image=None, is_top=False, is_season_top=False, mode="mp")
    assert ok is True

    # FTS search by weapon name should return our record
    results = db_adapter.search_attachments_fts("M4", limit=10)
    assert isinstance(results, list)
    assert _find_in_results(results, code)


def test_fuzzy_search_weapons(db_adapter):
    # Adapter exposes fuzzy_engine via attribute delegation
    engine = getattr(db_adapter, "fuzzy_engine", None)
    assert engine is not None

    # Rebuild index to include current data
    engine.clear_cache()
    engine.build_search_index(force=True)

    matches = engine.fuzzy_match_weapons("M4", threshold=60, limit=5)
    # Expect at least one match for weapon 'M4'
    assert any(name == "M4" for name, score in matches)
