import os
import uuid
import time
import pathlib
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode, quote
import psycopg
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SQL_FILE = ROOT / "scripts" / "init_postgres.sql"


def _dsn_with_search_path(base_dsn: str, schema: str) -> str:
    """Attach search_path to a DSN.
    - If base_dsn is a URI (postgresql://...), add query param options with %20 (not '+').
    - If base_dsn is DSN keywords (user=... dbname=...), append options with proper quoting.
    """
    opt_value = f"-c search_path={schema}"

    # Heuristic: treat as URI if it looks like a URL
    if base_dsn.startswith("postgres://") or base_dsn.startswith("postgresql://"):
        url = urlsplit(base_dsn)
        query = parse_qs(url.query, keep_blank_values=True)
        # Replace/append options; libpq expects spaces, not '+', so force %20 encoding via quote_via
        existing = query.get("options", [])
        if existing:
            existing.append(opt_value)
            merged = " ".join(existing)
        else:
            merged = opt_value
        new_query = urlencode({**query, "options": merged}, doseq=True, quote_via=quote)
        return urlunsplit((url.scheme, url.netloc, url.path, new_query, url.fragment))

    # Fallback: DSN keyword style (user=... password=...)
    # Surround value with single quotes to preserve the space inside
    if "options=" in base_dsn:
        return base_dsn + f" options='-c search_path={schema}'"
    return base_dsn + f" options='-c search_path={schema}'"


@pytest.fixture(scope="session")
def test_schema_dsn() -> str:
    base_dsn = os.environ.get("DATABASE_URL")
    if not base_dsn:
        pytest.skip("DATABASE_URL is not set; integration tests skipped")
    schema = f"test_pytest_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    # Create schema on base connection (public)
    with psycopg.connect(base_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
        conn.commit()

    # Prefer environment-based configuration to avoid URI encoding pitfalls
    os.environ["PGOPTIONS"] = f"-c search_path={schema}"
    test_dsn = base_dsn

    # Apply schema SQL into the test schema by setting search_path via DSN options
    stmts = []
    try:
        sql = SQL_FILE.read_text(encoding="utf-8")
        stmts = [s.strip() for s in sql.split(";") if s.strip()]
    except Exception as e:
        pytest.skip(f"Cannot read init_postgres.sql: {e}")

    with psycopg.connect(test_dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            # Ensure search_path is set (redundant with PGOPTIONS, but safe)
            cur.execute(f"SET search_path TO {schema}")
            # Ensure extensions for FTS (pg_trgm must be in the schema or public)
            try:
                # Try creating in current schema first
                cur.execute(f"CREATE EXTENSION IF NOT EXISTS pg_trgm SCHEMA {schema}")
            except Exception:
                # Fallback: try public schema (most common setup)
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                except Exception:
                    pass
            for s in stmts:
                try:
                    cur.execute(s)
                except Exception:
                    # Non-fatal; many statements are IF NOT EXISTS
                    pass

    yield test_dsn

    # Teardown: drop the schema (best-effort)
    try:
        with psycopg.connect(base_dsn) as conn:
            with conn.cursor() as cur:
                cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            conn.commit()
    except Exception:
        pass

    # Restore PGOPTIONS
    os.environ.pop("PGOPTIONS", None)


@pytest.fixture()
def db_adapter(test_schema_dsn):
    # Point adapter to the test schema DSN
    old_dsn = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = test_schema_dsn
    try:
        # Reset singleton instance
        import importlib
        from core.database import database_adapter as da
        importlib.reload(da)
        adapter = da.get_database_adapter()
        yield adapter
    finally:
        # Restore env
        if old_dsn is not None:
            os.environ["DATABASE_URL"] = old_dsn
        else:
            os.environ.pop("DATABASE_URL", None)
