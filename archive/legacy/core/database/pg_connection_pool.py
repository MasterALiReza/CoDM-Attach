"""
PostgreSQL Connection Pool Implementation
برای مدیریت بهینه connection ها و پشتیبانی از 1000+ کاربر همزمان
"""

import os
import psycopg
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from contextlib import contextmanager
from typing import Optional, Dict, Any
import threading
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class PostgreSQLConnectionPool:
    """
    Production-ready Connection Pool برای PostgreSQL
    
    Features:
    - Thread-safe connection pooling
    - Automatic reconnection on failure
    - Health checks and monitoring
    - Query performance tracking
    - Connection statistics
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern برای اطمینان از یک pool واحد"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, database_url: str = None, pool_size: int = 20, max_overflow: int = 10):
        """
        Initialize PostgreSQL connection pool
        
        Args:
            database_url: PostgreSQL connection string
            pool_size: تعداد connection های ثابت (default 20)
            max_overflow: حداکثر connection های موقت (default 10)
        """
        # جلوگیری از reinit در Singleton
        if hasattr(self, '_initialized'):
            return
            
        if database_url is None:
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise ValueError("DATABASE_URL is required for PostgreSQL")
        
        self.database_url = database_url
        self.pool_size = int(os.getenv('DB_POOL_SIZE', pool_size))
        self.max_overflow = int(os.getenv('DB_POOL_MAX_OVERFLOW', max_overflow))
        
        # Statistics
        self.stats = {
            'connections_created': 0,
            'connections_reused': 0,
            'connections_failed': 0,
            'queries_executed': 0,
            'slow_queries': 0,
            'errors': 0,
            'last_error': None,
            'start_time': datetime.now()
        }
        
        # Performance settings
        self.slow_query_threshold = float(os.getenv('SLOW_QUERY_THRESHOLD', 0.1))  # 100ms
        
        # Initialize pool
        self._init_pool()
        self._initialized = True
        
        logger.info(f"PostgreSQL Connection Pool initialized: {self.pool_size} + {self.max_overflow} overflow")
    
    def _init_pool(self):
        """Initialize psycopg3 connection pool"""
        try:
            # Connection pool configuration
            self._pool = ConnectionPool(
                conninfo=self.database_url,
                min_size=2,  # Minimum connections
                max_size=self.pool_size + self.max_overflow,  # Maximum connections
                kwargs={
                    'row_factory': dict_row,  # Return rows as dictionaries
                    'autocommit': False,  # Manual transaction control
                    'prepare_threshold': 5,  # Prepare statements after 5 uses
                },
                configure=self._configure_connection,
                check=ConnectionPool.check_connection,
                max_idle=600,  # Close idle connections after 10 minutes
                max_lifetime=3600,  # Recycle connections after 1 hour
                timeout=30,  # Connection timeout
                name='codm_bot_pool'
            )
            
            # Test connection
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT version() as version")
                result = cursor.fetchone()
                version = result['version'] if result else 'Unknown'
                logger.info(f"Connected to PostgreSQL: {version.split(',')[0]}")
                cursor.close()
            
            self.stats['connections_created'] += 1
            logger.info("Connection pool ready")
            
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            self.stats['connections_failed'] += 1
            self.stats['last_error'] = str(e)
            raise RuntimeError(f"PostgreSQL pool initialization failed: {e}")
    
    def _configure_connection(self, conn):
        """
        Configure each new connection
        
        Applied settings:
        - Statement timeout
        - Lock timeout  
        - Search path
        - Timezone
        
        Note: Must commit to avoid INTRANS status
        """
        try:
            with conn.cursor() as cursor:
                # Performance settings
                cursor.execute("SET statement_timeout = '30s'")  # 30 second query timeout
                cursor.execute("SET lock_timeout = '10s'")  # 10 second lock timeout
                cursor.execute("SET idle_in_transaction_session_timeout = '60s'")  # 60 second idle timeout
                
                # Application settings
                cursor.execute("SET TIME ZONE 'UTC'")
                cursor.execute("SET application_name = 'codm_bot'")
                
                # Try to enable pg_trgm (may fail if no superuser access)
                try:
                    cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                except Exception as ext_error:
                    logger.debug(f"Could not create pg_trgm extension: {ext_error}")
            
            # CRITICAL: Commit to clear INTRANS status
            conn.commit()
            logger.debug("Connection configured and committed")
            
        except Exception as e:
            logger.error(f"Error configuring connection: {e}")
            # Rollback to ensure clean state
            try:
                conn.rollback()
            except:
                pass
    
    @contextmanager
    def get_connection(self, timeout: float = 5.0):
        """
        Get connection from pool (context manager)
        
        Usage:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM ...")
                results = cursor.fetchall()
        """
        start_time = time.time()
        
        try:
            # Get connection from pool (psycopg pool handles cleanup automatically)
            with self._pool.connection(timeout=timeout) as conn:
                self.stats['connections_reused'] += 1
                
                # Yield connection for use
                yield conn
                # Connection is automatically returned to pool on exit
                
        except Exception as e:
            # Log error
            if 'PoolTimeout' in str(type(e).__name__):
                logger.error(f"Connection pool timeout after {timeout}s")
                self.stats['connections_failed'] += 1
                self.stats['last_error'] = f"Pool timeout: {e}"
                raise TimeoutError(f"Could not get connection from pool within {timeout}s")
            else:
                logger.error(f"Connection error: {e}")
                self.stats['errors'] += 1
                self.stats['last_error'] = str(e)
                raise
        
        finally:
            # Track performance
            elapsed = time.time() - start_time
            if elapsed > self.slow_query_threshold:
                self.stats['slow_queries'] += 1
                logger.warning(f"Slow connection acquisition: {elapsed:.3f}s")
    
    def execute_query(self, query: str, params: tuple = None, fetch_one: bool = False,
                     fetch_all: bool = False) -> Any:
        """
        Execute query with automatic connection management
        
        Args:
            query: SQL query (%s placeholders)
            params: Query parameters
            fetch_one: Return single row
            fetch_all: Return all rows
            
        Returns:
            Query results or None
        """
        start_time = time.time()
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Log slow queries
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"Executing: {query[:100]}...")
                
                # Execute query
                cursor.execute(query, params or ())
                self.stats['queries_executed'] += 1
                
                # Fetch results
                result = None
                if fetch_one:
                    result = cursor.fetchone()
                elif fetch_all:
                    result = cursor.fetchall()
                elif cursor.description:
                    # For INSERT/UPDATE with RETURNING
                    result = cursor.fetchall()
                
                cursor.close()
                
                # Track slow queries
                elapsed = time.time() - start_time
                if elapsed > self.slow_query_threshold:
                    self.stats['slow_queries'] += 1
                    logger.warning(f"Slow query ({elapsed:.3f}s): {query[:100]}...")
                
                return result
                
        except Exception as e:
            self.stats['errors'] += 1
            self.stats['last_error'] = str(e)
            logger.error(f"Query execution failed: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get pool statistics
        
        Returns:
            Dictionary with pool metrics
        """
        uptime = datetime.now() - self.stats['start_time']
        
        return {
            **self.stats,
            'uptime_seconds': uptime.total_seconds(),
            'pool_size': self.pool_size,
            'max_overflow': self.max_overflow,
            'active_connections': self._pool.get_stats()['requests_num'] if hasattr(self._pool, 'get_stats') else 0,
            'success_rate': (
                (self.stats['connections_reused'] / 
                 max(1, self.stats['connections_reused'] + self.stats['connections_failed'])) * 100
            )
        }
    
    def health_check(self) -> bool:
        """
        Check pool health
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            with self.get_connection(timeout=2.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                result = cursor.fetchone()
                cursor.close()
                return result is not None
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
    def close(self, timeout: float = 5.0):
        """Close all connections in pool"""
        try:
            if hasattr(self, '_pool') and self._pool:
                self._pool.close(timeout=timeout)
                logger.info("Connection pool closed")
        except Exception as e:
            logger.error(f"Error closing pool: {e}")
    
    def __del__(self):
        """Cleanup on deletion"""
        self.close()


# Global pool instance
_global_pool: Optional[PostgreSQLConnectionPool] = None


def get_pool(database_url: str = None, **kwargs) -> PostgreSQLConnectionPool:
    """
    Get or create global connection pool
    
    Args:
        database_url: PostgreSQL connection string
        **kwargs: Additional pool configuration
        
    Returns:
        PostgreSQLConnectionPool instance
    """
    global _global_pool
    
    if _global_pool is None:
        _global_pool = PostgreSQLConnectionPool(database_url, **kwargs)
    
    return _global_pool


def close_pool(timeout: float = 2.0):
    """Close global connection pool"""
    global _global_pool
    
    if _global_pool:
        _global_pool.close(timeout=timeout)
        _global_pool = None
