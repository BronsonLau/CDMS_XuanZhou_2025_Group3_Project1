"""
MongoDB store/inventory/order schemas and index setup for Bookstore.

This module doesn't change existing SQLite flows yet. It prepares
collections and indexes for a phased migration.
"""
from __future__ import annotations

from typing import Optional
from pymongo import TEXT

from pymongo.database import Database


def ensure_indexes(db: Optional[Database]) -> None:
    if db is None:
        return

    # users: already ensured via user path; _id unique by default

    # stores: owner mapping
    # {_id: store_id, owner_id}
    db["stores"].create_index("_id", unique=True)
    db["stores"].create_index("owner_id")

   
