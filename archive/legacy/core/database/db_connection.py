"""Database Connection Abstraction Layer
PostgreSQL connection management
"""

import os
from typing import Any, List, Dict, Optional, Union
from contextlib import contextmanager
from utils.logger import get_logger

logger = get_logger('database.connection', 'database.log')


class DatabaseConnection:
    """
    PostgreSQL Connection Layer
    این کلاس query placeholders را خودکار تبدیل می‌کند
    """
    
    def __init__(self, backend: str = None):
        """
        Initialize PostgreSQL connection
        
        Args:
            backend: Always 'postgres'
        """
        self.backend = 'postgres'
        self._connection = None
        self._init_postgres()
    
    
    def _init_postgres(self):
        """Initialize PostgreSQL connection"""
        try:
            import psycopg
            from psycopg.rows import dict_row
            
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                raise ValueError("DATABASE_URL not set for PostgreSQL")
            
            self._connection = psycopg.connect(db_url)
            logger.info(f"PostgreSQL connection initialized")
            
        except ImportError:
            logger.error("PostgreSQL driver not installed!")
            raise ImportError("Please install psycopg with: pip install psycopg[binary,pool]")
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")
            raise RuntimeError(f"PostgreSQL initialization failed: {e}")
    
    def _convert_query(self, query: str) -> str:
        """
        تبدیل query placeholders به PostgreSQL format
        
        تبدیل legacy placeholders به %s (PostgreSQL)
        """
        return query.replace('$PH$', '%s')
    
    def execute(self, query: str, params: tuple = None) -> Any:
        """
        اجرای query با placeholder conversion خودکار
        
        Args:
            query: SQL query
            params: پارامترها
            
        Returns:
            cursor object
        """
        converted_query = self._convert_query(query)
        
        cursor = self._connection.cursor()
        
        if params:
            cursor.execute(converted_query, params)
        else:
            cursor.execute(converted_query)
        
        return cursor
    
    def fetchone(self, query: str, params: tuple = None) -> Optional[Dict]:
        """اجرای query و برگرداندن یک رکورد"""
        cursor = self.execute(query, params)
        result = cursor.fetchone()
        cursor.close()
        
        if result:
            # Convert to dict for PostgreSQL
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, result))
        
        return None
    
    def fetchall(self, query: str, params: tuple = None) -> List[Dict]:
        """اجرای query و برگرداندن همه رکوردها"""
        cursor = self.execute(query, params)
        results = cursor.fetchall()
        cursor.close()
        
        # Convert to list of dicts for PostgreSQL
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in results]
    
    def commit(self):
        """Commit transaction"""
        self._connection.commit()
    
    def rollback(self):
        """Rollback transaction"""
        self._connection.rollback()
    
    def close(self):
        """بستن connection"""
        if self._connection:
            self._connection.close()
            logger.info(f"{self.backend} connection closed")
    
    @property
    def connection(self):
        """دسترسی مستقیم به connection (برای backward compatibility)"""
        return self._connection
    
    @contextmanager
    def transaction(self):
        """Context manager برای transaction"""
        try:
            yield self._connection
            self.commit()
        except Exception:
            self.rollback()
            raise
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        return False


class ConnectionPool:
    """
    Connection Pool برای PostgreSQL
    """
    
    def __init__(self, backend: str = None, pool_size: int = 20):
        self.backend = 'postgres'  # Always PostgreSQL
        self.pool_size = pool_size
        self._pool = None
        self._init_postgres_pool()
    
    def _init_postgres_pool(self):
        """Initialize PostgreSQL connection pool"""
        try:
            from psycopg_pool import ConnectionPool
            
            db_url = os.getenv('DATABASE_URL')
            if not db_url:
                raise ValueError("DATABASE_URL not set")
            
            self._pool = ConnectionPool(
                minconn=1,
                maxconn=self.pool_size,
                dsn=db_url
            )
            
            logger.info(f"PostgreSQL connection pool initialized: {self.pool_size} connections")
            
        except Exception as e:
            logger.error(f"PostgreSQL pool initialization failed: {e}")
            raise RuntimeError(f"PostgreSQL pool initialization failed: {e}")
    
    def get_connection(self) -> DatabaseConnection:
        """دریافت connection از pool"""
        if self._pool:
            raw_conn = self._pool.getconn()
            # Wrap در DatabaseConnection
            db_conn = DatabaseConnection('postgres')
            return db_conn
        raise RuntimeError("Connection pool not initialized")
    
    def return_connection(self, conn: DatabaseConnection):
        """برگرداندن connection به pool"""
        if self._pool:
            self._pool.putconn(conn._connection)
    
    @contextmanager
    def connection(self):
        """Context manager برای دریافت connection"""
        conn = self.get_connection()
        try:
            yield conn
        finally:
            self.return_connection(conn)
    
    def close_all(self):
        """بستن تمام connections"""
        if self._pool:
            self._pool.closeall()
            logger.info("PostgreSQL connection pool closed")
        elif hasattr(self, '_single_connection'):
            self._single_connection.close()
_pool = None

def get_connection_pool() -> ConnectionPool:
    """دریافت connection pool singleton"""
    global _pool
    
    if _pool is None:
        pool_size = int(os.getenv('DB_POOL_SIZE', 20))
        _pool = ConnectionPool(pool_size=pool_size)
    
    return _pool
