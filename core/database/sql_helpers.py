"""
SQL Helper Functions - PostgreSQL Only
Helper functions for PostgreSQL database operations (PG-only)
"""

import os
from typing import Optional, Union
from datetime import datetime, timedelta


def get_backend() -> str:
    """تشخیص backend فعلی از environment"""
    return os.getenv('DATABASE_BACKEND', 'postgres').lower()


def get_date_interval(days_ago: int, backend: Optional[str] = None) -> str:
    """
    تولید query برای محاسبه تاریخ N روز قبل
    
    Args:
        days_ago: تعداد روزهای قبل
        backend: target backend (اگر None باشد از env خوانده می‌شود)
    
    Returns:
        Query string سازگار با backend
        
    Examples:
        >>> get_date_interval(7, 'legacy')
        "DATE('now', '-7 days')"
        >>> get_date_interval(7, 'postgres')
        "CURRENT_DATE - INTERVAL '7 days'"
    """
    # PostgreSQL only
    return f"CURRENT_DATE - INTERVAL '{days_ago} days'"


def get_datetime_interval(days_ago: int, backend: Optional[str] = None) -> str:
    """
    تولید query برای محاسبه datetime N روز قبل
    
    Args:
        days_ago: تعداد روزهای قبل
        backend: target backend
    
    Returns:
        Query string سازگار با backend
        
    Examples:
        >>> get_datetime_interval(30, 'legacy')
        "datetime('now', '-30 days')"
        >>> get_datetime_interval(30, 'postgres')
        "CURRENT_TIMESTAMP - INTERVAL '30 days'"
    """
    # PostgreSQL only
    return f"CURRENT_TIMESTAMP - INTERVAL '{days_ago} days'"


def get_current_date(backend: Optional[str] = None) -> str:
    """
    تولید query برای تاریخ امروز
    
    Returns:
        Query string سازگار با backend
    """
    # PostgreSQL only
    return "CURRENT_DATE"


def get_current_timestamp(backend: Optional[str] = None) -> str:
    """
    تولید query برای timestamp فعلی
    
    Returns:
        Query string سازگار با backend
    """
    # PostgreSQL only
    return "CURRENT_TIMESTAMP"


def build_upsert_query(
    table: str,
    columns: list,
    conflict_columns: list,
    update_columns: Optional[list] = None,
    backend: Optional[str] = None
) -> str:
    """
    ساخت query UPSERT سازگار
    
    Args:
        table: نام جدول
        columns: لیست ستون‌های INSERT
        conflict_columns: ستون‌هایی که conflict دارند
        update_columns: ستون‌هایی که باید UPDATE شوند (اگر None باشد همه به‌جز conflict)
        backend: target backend
    
    Returns:
        Query string کامل با placeholders
        
    Example:
        >>> build_upsert_query('users', ['id', 'name'], ['id'], ['name'], 'legacy')
        "INSERT OR REPLACE INTO users (id, name) VALUES (%s, %s)"
        >>> build_upsert_query('users', ['id', 'name'], ['id'], ['name'], 'postgres')
        "INSERT INTO users (id, name) VALUES (%s, %s) ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name"
    """
    # PostgreSQL only
    placeholder = '%s'
    placeholders = ', '.join([placeholder] * len(columns))
    columns_str = ', '.join(columns)
    conflict_str = ', '.join(conflict_columns)
    if update_columns is None:
        update_columns = [col for col in columns if col not in conflict_columns]
    if update_columns:
        update_str = ', '.join([f"{col} = EXCLUDED.{col}" for col in update_columns])
        return f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT ({conflict_str}) DO UPDATE SET {update_str}"
    else:
        return f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT ({conflict_str}) DO NOTHING"


def build_insert_ignore_query(
    table: str,
    columns: list,
    backend: Optional[str] = None
) -> str:
    """
    ساخت query INSERT IGNORE سازگار
    
    Args:
        table: نام جدول
        columns: لیست ستون‌ها
        backend: target backend
    
    Returns:
        Query string کامل
    """
    # PostgreSQL only
    placeholder = '%s'
    placeholders = ', '.join([placeholder] * len(columns))
    columns_str = ', '.join(columns)
    return f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"


def get_returning_clause(column: str = 'id', backend: Optional[str] = None) -> str:
    """
    تولید RETURNING clause برای دریافت ID بعد از INSERT
    
    Args:
        column: نام ستونی که باید برگردانده شود
        backend: target backend
    
    Returns:
        RETURNING clause یا empty string
    """
    # PostgreSQL only
    return f" RETURNING {column}"


def adapt_placeholder(query: str, backend: Optional[str] = None) -> str:
    """
    تبدیل placeholders در query
    
    Args:
        query: Query با placeholder
        backend: target backend
    
    Returns:
        Query با placeholder صحیح
    """
    # PostgreSQL only - convert $ placeholders to %s if present
    parts = []
    in_string = False
    quote_char = None
    i = 0
    while i < len(query):
        char = query[i]
        if char in ('"', "'") and (i == 0 or query[i-1] != '\\'):
            if not in_string:
                in_string = True
                quote_char = char
            elif char == quote_char:
                in_string = False
                quote_char = None
        if char == '$' and not in_string:
            parts.append('%s')
        else:
            parts.append(char)
        i += 1
    return ''.join(parts)


# کلاس wrapper برای queries سازگار
class SQLQuery:
    """کلاس کمکی برای ساخت queries database-agnostic"""
    
    def __init__(self, backend: Optional[str] = None):
        self.backend = backend or get_backend()
    
    def placeholder(self) -> str:
        """دریافت placeholder مناسب"""
        return '%s'
    
    def date_interval(self, days_ago: int) -> str:
        """محاسبه تاریخ N روز قبل"""
        return get_date_interval(days_ago, self.backend)
    
    def datetime_interval(self, days_ago: int) -> str:
        """محاسبه datetime N روز قبل"""
        return get_datetime_interval(days_ago, self.backend)
    
    def current_date(self) -> str:
        """تاریخ امروز"""
        return get_current_date(self.backend)
    
    def current_timestamp(self) -> str:
        """timestamp فعلی"""
        return get_current_timestamp(self.backend)
    
    def upsert(self, table: str, columns: list, conflict_columns: list, 
               update_columns: Optional[list] = None) -> str:
        """ساخت upsert query"""
        return build_upsert_query(table, columns, conflict_columns, 
                                 update_columns, self.backend)
    
    def insert_ignore(self, table: str, columns: list) -> str:
        """ساخت insert ignore query"""
        return build_insert_ignore_query(table, columns, self.backend)
    
    def returning(self, column: str = 'id') -> str:
        """RETURNING clause"""
        return get_returning_clause(column, self.backend)


# ========== Full-Text Search Helpers ==========

def build_fts_where_clause(
    query: str,
    search_columns: list,
    backend: Optional[str] = None
) -> str:
    """
    ساخت WHERE clause برای Full-Text Search
    
    Args:
        query: متن جستجو
        search_columns: لیست ستون‌های جستجو (مثل ['name', 'code'])
        backend: target backend
    
    Returns:
        WHERE clause string
    
    Examples:
        Legacy FTS:
        >>> build_fts_where_clause('M4', ['name', 'code'], 'legacy')
        "attachments_fts MATCH %s"
        
        PostgreSQL (pg_trgm):
        >>> build_fts_where_clause('M4', ['name', 'code'], 'postgres')
        "name %% %s OR code %% %s"
    """
    # PostgreSQL only - pg_trgm similarity search
    conditions = " OR ".join([f"{col} %% %s" for col in search_columns])
    return conditions


def build_fts_order_clause(
    query: str,
    primary_column: str,
    backend: Optional[str] = None
) -> str:
    """
    ساخت ORDER BY clause برای Full-Text Search
    
    Args:
        query: متن جستجو
        primary_column: ستون اصلی برای مرتب‌سازی
        backend: target backend
    
    Returns:
        ORDER BY clause string
    
    Examples:
        Legacy FTS:
        >>> build_fts_order_clause('M4', 'name', 'legacy')
        "rank"
        
        PostgreSQL (pg_trgm):
        >>> build_fts_order_clause('M4', 'name', 'postgres')
        "similarity(name, %s) DESC"
    """
    # PostgreSQL only - pg_trgm similarity ordering
    return f"similarity({primary_column}, %s) DESC"


def get_fts_params(
    query: str,
    search_columns: list,
    backend: Optional[str] = None
) -> tuple:
    """
    دریافت پارامترهای مورد نیاز برای FTS query
    
    Args:
        query: متن جستجو
        search_columns: لیست ستون‌های جستجو
        backend: target backend
    
    Returns:
        Tuple از پارامترها برای query
    
    Examples:
        Legacy:
        >>> get_fts_params('M4', ['name', 'code'], 'legacy')
        ('M4',)
        
        PostgreSQL:
        >>> get_fts_params('M4', ['name', 'code'], 'postgres')
        ('M4', 'M4', 'M4')  # برای WHERE + ORDER BY
    """
    # PostgreSQL only - one per WHERE column plus one for ORDER BY
    num_columns = len(search_columns)
    return tuple([query] * (num_columns + 1))


def build_fts_query(
    query: str,
    search_columns: list,
    primary_column: str = None,
    backend: Optional[str] = None
) -> tuple:
    """
    ساخت کامل FTS query (WHERE + ORDER + params)
    
    Args:
        query: متن جستجو
        search_columns: لیست ستون‌های جستجو
        primary_column: ستون اصلی برای ordering (default: اولین ستون)
        backend: target backend
    
    Returns:
        (where_clause, order_clause, params)
    
    Examples:
        >>> where, order, params = build_fts_query('M4', ['name', 'code'])
        # Legacy: ("attachments_fts MATCH %s", "rank", ("M4",))
        # PostgreSQL: ("name %% %s OR code %% %s", "similarity(name, %s) DESC", ("M4", "M4", "M4"))
    """
    if primary_column is None:
        primary_column = search_columns[0]
    
    where_clause = build_fts_where_clause(query, search_columns, backend)
    order_clause = build_fts_order_clause(query, primary_column, backend)
    params = get_fts_params(query, search_columns, backend)
    
    return (where_clause, order_clause, params)


def get_fts_similarity_threshold(backend: Optional[str] = None) -> float:
    """
    دریافت similarity threshold برای FTS
    
    Args:
        backend: target backend
    
    Returns:
        Threshold value (0.0 - 1.0)
    
    Note:
        - Legacy FTS: همیشه 0 (همه نتایج برمی‌گردند)
        - PostgreSQL pg_trgm: پیش‌فرض 0.3 (قابل تنظیم)
    """
    # PostgreSQL only
    threshold = os.getenv('PG_TRGM_THRESHOLD', '0.3')
    return float(threshold)
