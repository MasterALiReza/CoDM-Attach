import os
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

HERE = os.path.dirname(__file__)
ROOT = Path(HERE).parent
SQL_PATH = os.path.join(HERE, "init_postgres.sql")


def _load_database_url() -> str | None:
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    # Fallback: read from .env in project root
    env_path = ROOT / ".env"
    try:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('DATABASE_URL='):
                    # Support quoted or plain
                    value = line.split('=', 1)[1].strip().strip('"').strip("'")
                    if value:
                        os.environ['DATABASE_URL'] = value
                        return value
    except Exception:
        pass
    return None


def main() -> int:
    dsn = _load_database_url()
    if not dsn:
        print("ERROR: DATABASE_URL not set (env) and not found in .env", file=sys.stderr)
        return 2

    # Build target list from CLI args: files or directories of .sql
    args = sys.argv[1:]
    targets: list[Path] = []
    if args:
        for arg in args:
            p = Path(arg)
            if not p.is_absolute():
                p = (Path(HERE) / p).resolve()
            if p.is_dir():
                # All .sql files in directory, sorted by name
                for f in sorted(p.glob('*.sql')):
                    targets.append(f)
            elif p.suffix.lower() == '.sql' and p.exists():
                targets.append(p)
            else:
                print(f"WARN: skipping invalid target: {arg}", file=sys.stderr)
    else:
        targets = [Path(SQL_PATH)]

    total_statements = 0
    applied = 0
    with psycopg.connect(dsn) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            for tpath in targets:
                try:
                    sql = tpath.read_text(encoding='utf-8')
                except Exception as e:
                    print(f"ERROR: cannot read SQL file: {tpath} -> {e}", file=sys.stderr)
                    continue
                stmts = [s.strip() for s in sql.split(';') if s.strip()]
                total_statements += len(stmts)
                for s in stmts:
                    try:
                        cur.execute(s)
                        applied += 1
                    except Exception as e:
                        print(f"WARN: failed statement head: {s[:120]!r} -> {e}", file=sys.stderr)

    # Quick verification of key tables
    verify_tables = [
        'user_attachments',
        'user_attachment_engagement',
        'suggested_attachments',
        'user_attachment_settings',
        'ua_stats_cache',
        'ua_top_weapons_cache',
        'ua_top_users_cache',
        'data_health_checks',
        'data_quality_metrics',
    ]
    missing: list[str] = []
    try:
        with psycopg.connect(dsn, row_factory=dict_row) as vconn:
            with vconn.cursor() as vcur:
                vcur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                    """
                )
                existing = {row.get('table_name') for row in vcur.fetchall()}
        missing = [t for t in verify_tables if t not in existing]
    except Exception:
        # Verification is best-effort
        pass

    print(f"Applied {applied}/{total_statements} statements successfully from {len(targets)} file(s)")
    if missing:
        print(f"Missing tables after apply: {', '.join(missing)}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
