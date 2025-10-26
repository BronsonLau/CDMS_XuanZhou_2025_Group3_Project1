"""
MongoDB connection utilities for the Bookstore project.

Default connection:
- URI: env MONGO_URI or 'mongodb://localhost:27017'
- DB : env MONGO_DB  or 'project1'

Usage:
    from be.model import mongo_store
    db = mongo_store.get_db()
    users = db["user"]
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pymongo import MongoClient
from pymongo.database import Database


@lru_cache(maxsize=1)
def _get_client() -> MongoClient:
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    # MongoClient is thread-safe and designed to be reused
    return MongoClient(uri)


def get_db_name() -> str:
    return os.getenv("MONGO_DB", os.getenv("MONGODB_DB", "project1"))


def get_db() -> Database:
    client = _get_client()
    return client[get_db_name()]


def ensure_indexes(db: Optional[Database] = None) -> None:
    """Create necessary indexes. Safe to call multiple times.

    Collections and indexes we may rely on initially:
    - user: _id unique (default), balance field for queries can be left unindexed for now
    - user_store: store_id unique
    - store: composite key (store_id, book_id) unique, and optional filters
    - order_status: index on (order_id, ts desc)
    """
    # IMPORTANT: PyMongo Database objects do not support truthiness checks.
    # Using `db or get_db()` will raise NotImplementedError. Compare to None explicitly.
    if db is None:
        db = get_db()
    # user: _id is implicitly unique in MongoDB; no explicit index needed
    # Additional indexes for other collections will be added as models migrate.
