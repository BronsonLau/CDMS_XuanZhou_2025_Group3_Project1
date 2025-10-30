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

    # inventory per store/book
    # {store_id, book_id, book_info, stock_level, title, author, isbn, pub_year, pages, price}
    db["inventory"].create_index([("store_id", 1), ("book_id", 1)], unique=True)
    db["inventory"].create_index([("store_id", 1), ("stock_level", 1)])
    # text/attribute indexes to speed search-like operations
    db["inventory"].create_index([("store_id", 1), ("title", 1)])
    db["inventory"].create_index([("store_id", 1), ("author", 1)])
    db["inventory"].create_index([("store_id", 1), ("isbn", 1)])
    db["inventory"].create_index([("title", 1), ("book_id", 1)])
    db["inventory"].create_index("title")
    db["inventory"].create_index("author")
    db["inventory"].create_index("isbn")
    db["inventory"].create_index("pub_year")
    db["inventory"].create_index("pages")
    db["inventory"].create_index("price")

    # Full-text index to optimize keyword search across multiple fields
    # Include redundant fields and a pre-computed text blob from book_info (tags/content/etc.)
    try:
        db["inventory"].create_index(
            [("title", TEXT), ("author", TEXT), ("isbn", TEXT), ("text_blob", TEXT)],
            name="inventory_text_index",
            default_language="none",
        )
    except Exception:
        # Older Mongo versions or permissions may fail; search will fall back to regex
        pass

    # orders header
    # {_id: order_id, user_id, store_id, created_ts}
    db["orders"].create_index("_id", unique=True)
    db["orders"].create_index("user_id")
    db["orders"].create_index("store_id")

    # order details
    # {order_id, book_id, count, price}
    db["order_details"].create_index("order_id")

    # order status history: {order_id, status, ts, user_id, store_id}
    db["order_status"].create_index("order_id")
    db["order_status"].create_index([("order_id", 1), ("ts", 1)])
    db["order_status"].create_index([("order_id", 1), ("status", 1), ("ts", 1)])
