import os
from enum import Enum
from typing import Optional, Union

from .database_pg_proxy import DatabasePostgresProxy
from .database_pg import DatabasePostgres

class DatabaseMode(Enum):
    """Database operation modes"""
    READ = 'read'
    WRITE = 'write'

class DatabaseBackend(Enum):
    """Supported database backends"""
    POSTGRES = 'postgres'
    SQLITE = 'sqlite'  # Legacy support

# Type alias for the adapter interface
DatabaseAdapter = Union[DatabasePostgresProxy, DatabasePostgres]

_db_instance: Optional[DatabaseAdapter] = None

def get_database_adapter(backend: DatabaseBackend = DatabaseBackend.POSTGRES) -> DatabaseAdapter:
    """
    Factory function to get the database adapter.
    Returns a singleton instance of DatabasePostgresProxy.
    
    Args:
        backend: Database backend to use (default: POSTGRES)
    
    Returns:
        DatabaseAdapter: The database adapter instance
    """
    global _db_instance
    
    if _db_instance is None:
        # Get database URL from environment
        database_url = os.getenv('DATABASE_URL')
        
        # Initialize PostgreSQL Proxy (which handles connection pooling and logic)
        _db_instance = DatabasePostgresProxy(database_url)
        
    return _db_instance
