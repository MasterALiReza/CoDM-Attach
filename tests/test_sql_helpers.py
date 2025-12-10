from core.database.sql_helpers import (
    get_date_interval,
    get_datetime_interval,
    get_current_date,
    get_current_timestamp,
    build_fts_where_clause,
    build_fts_order_clause,
    get_fts_params,
    build_fts_query,
    adapt_placeholder,
    SQLQuery,
)


def test_get_date_interval():
    s = get_date_interval(7)
    assert "INTERVAL '7 days'" in s


def test_get_datetime_interval():
    s = get_datetime_interval(30)
    assert "INTERVAL '30 days'" in s


def test_get_current_date_and_timestamp():
    assert get_current_date() == "CURRENT_DATE"
    assert get_current_timestamp() == "CURRENT_TIMESTAMP"


def test_adapt_placeholder_basic():
    q = "SELECT '$', $ FROM t"
    out = adapt_placeholder(q)
    assert out == "SELECT '$', %s FROM t"


def test_build_fts_where_and_order():
    where = build_fts_where_clause("M4", ["name", "code"])
    assert where == "name %% %s OR code %% %s"
    order = build_fts_order_clause("M4", "name")
    assert order == "similarity(name, %s) DESC"


def test_get_fts_params_and_query():
    where, order, params = build_fts_query("M4", ["name", "code"])
    assert where == "name %% %s OR code %% %s"
    assert order == "similarity(name, %s) DESC"
    assert params == ("M4", "M4", "M4")


def test_sqlquery_helpers():
    q = SQLQuery()
    assert q.placeholder() == "%s"
    assert q.current_date() == "CURRENT_DATE"
    assert q.current_timestamp() == "CURRENT_TIMESTAMP"
    upsert = q.upsert("users", ["id", "name"], ["id"], ["name"])
    assert "ON CONFLICT (id)" in upsert
