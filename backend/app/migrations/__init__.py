"""
Data migration tracking and execution module.

Provides utilities for running and tracking schema/data migrations at
application startup.

Exports:
    - CRUD: get_migrations_not_executed,
      mark_executed
    - Utils: check_migrations_not_executed
"""

from .crud import get_migrations_not_executed
from .service import mark_executed
from .utils import check_migrations_not_executed

__all__ = [
    "check_migrations_not_executed",
    "get_migrations_not_executed",
    "mark_executed",
]
