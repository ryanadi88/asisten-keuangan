"""
Database storage package initializer and factory function.
"""

import logging
from typing import Optional

from config import settings
from database.base import StorageBackend
from database.sqlite_db import SQLiteBackend

logger = logging.getLogger(__name__)

_storage_instance: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    """
    Factory function returning the configured StorageBackend (SQLite or Google Sheets).
    Defaults to SQLiteBackend if Google Sheets is not configured or throws an error.
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    backend_type = settings.DB_BACKEND.lower().strip()

    if backend_type == "gsheets":
        try:
            from database.gsheets_db import GoogleSheetsBackend
            _storage_instance = GoogleSheetsBackend()
            logger.info("Using Google Sheets Storage Backend")
            return _storage_instance
        except Exception as e:
            logger.warning(
                "Failed to initialize Google Sheets backend (%s). Falling back to SQLite.", e
            )

    _storage_instance = SQLiteBackend()
    logger.info("Using SQLite Storage Backend: %s", settings.SQLITE_DB_PATH)
    return _storage_instance
