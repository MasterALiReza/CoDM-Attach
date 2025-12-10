"""
Analytics Database Helper
Helper برای استفاده آسان از database در analytics modules
"""

from typing import List, Dict, Any, Optional
from contextlib import contextmanager

class AnalyticsDBHelper:
    """Helper class برای analytics با PostgreSQL support"""
    
    def __init__(self, db_adapter):
        self.db = db_adapter
    
    @contextmanager
    def _get_connection(self):
        """Get PostgreSQL database connection"""
        # PostgreSQL with connection pool
        with self.db.get_connection() as conn:
            yield conn
    
    def execute_query(self, query: str, params: tuple = (), fetch_all: bool = False, fetch_one: bool = False):
        """Execute PostgreSQL query"""
        
        # Ensure PostgreSQL placeholders
        query = query.replace('?', '%s')
        
        # Delegate to adapter which forwards to Postgres proxy
        if hasattr(self.db, 'execute_query'):
            return self.db.execute_query(
                query, params,
                fetch_all=fetch_all,
                fetch_one=fetch_one
            )
        # Fallback: manual execution
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            if fetch_one:
                return cur.fetchone()
            if fetch_all:
                return cur.fetchall()
            conn.commit()
            return None
    
    def get_stats(self, days: int = 30) -> Dict:
        """Get analytics stats for last N days"""
        try:
            days = int(days)
        except Exception:
            days = 30
        days = max(1, min(days, 365))
        
        # PostgreSQL date query: use make_interval for safe parameter binding
        date_filter = "created_at >= NOW() - make_interval(days => %s)"
        params = (days,)
        
        query = f"""
            SELECT COUNT(*) as total
            FROM analytics_events  
            WHERE {date_filter}
        """
        
        result = self.execute_query(query, params, fetch_one=True)
        return result or {'total': 0}
