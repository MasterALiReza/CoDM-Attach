import pytest
import psycopg
from psycopg.rows import dict_row

pytestmark = pytest.mark.integration


def test_connection_and_schema_columns(db_adapter):
    # Basic connection smoke test
    with db_adapter.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 AS one")
        row = cur.fetchone()
        assert (row or {}).get("one") == 1
        cur.close()

    # Ensure attachments columns ensured by schema guard exist
    with db_adapter.get_connection() as conn:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = %s
            """,
            ("attachments",),
        )
        cols = {r["column_name"] for r in cur.fetchall()}
        cur.close()

    assert "updated_at" in cols
    assert "order_index" in cols
