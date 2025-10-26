"""
Import SQLite book.db into MongoDB collections used by BookDB.

Usage (Windows PowerShell):

  # Small dataset (default)
  python .\bookstore\script\import_sqlite_bookdb_to_mongo.py --sqlite .\bookstore\fe\data\book.db --collection bookdb_small --drop-first

  # Large dataset (book_lx.db)
  python .\bookstore\script\import_sqlite_bookdb_to_mongo.py --sqlite "C:\\path\\to\\book_lx.db" --collection bookdb_large --drop-first

Environment variables for MongoDB connection:
  - MONGO_URI (default: mongodb://localhost:27017)
  - MONGO_DB  (default: project1)

This script maps the SQLite schema 1:1 to Mongo documents. The 'picture' BLOB
is stored as raw binary under the 'picture' field, as expected by fe/access/book.py.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Iterable, Tuple, Any, Dict

# Ensure we can import 'be.model.mongo_store' when running from repo root
_THIS = Path(__file__).resolve()
sys.path.append(str(_THIS.parents[1]))  # add '<repo>/bookstore' to sys.path

from be.model import mongo_store


FIELDS = [
    "id",
    "title",
    "author",
    "publisher",
    "original_title",
    "translator",
    "pub_year",
    "pages",
    "price",
    "currency_unit",
    "binding",
    "isbn",
    "author_intro",
    "book_intro",
    "content",
    "tags",
    "picture",
]


def iter_rows(cur: sqlite3.Cursor) -> Iterable[Tuple[Any, ...]]:
    while True:
        rows = cur.fetchmany(1000)
        if not rows:
            break
        for r in rows:
            yield r


def normalize_row(row: Tuple[Any, ...]) -> Dict[str, Any]:
    d: Dict[str, Any] = {k: row[i] for i, k in enumerate(FIELDS)}
    # Normalize types
    # pages/price are ints when possible
    for key in ("pages", "price"):
        v = d.get(key)
        try:
            if v is not None:
                d[key] = int(v)
        except Exception:
            # keep original when not convertible
            pass
    # tags: try JSON-like split; if simple string, split by '\n' or ','
    tags = d.get("tags")
    if isinstance(tags, (bytes, bytearray)):
        try:
            tags = tags.decode("utf-8", errors="ignore")
        except Exception:
            tags = ""
    if isinstance(tags, str):
        txt = tags.strip()
        if txt.startswith("[") and txt.endswith("]"):
            # naive JSON list parsing without importing json to avoid footguns
            # fall back to comma split if parsing fails
            try:
                import json as _json

                d["tags"] = list(_json.loads(txt))
            except Exception:
                d["tags"] = [t.strip() for t in txt.replace("\n", ",").split(",") if t.strip()]
        else:
            d["tags"] = [t.strip() for t in txt.replace("\n", ",").split(",") if t.strip()]
    elif isinstance(tags, list):
        d["tags"] = tags
    else:
        d["tags"] = []
    # picture: keep as-is (bytes or None)
    return d


def import_sqlite(sqlite_path: str, collection: str, drop_first: bool = False) -> int:
    if not os.path.exists(sqlite_path):
        raise FileNotFoundError(sqlite_path)

    dbm = mongo_store.get_db()
    col = dbm[collection]
    if drop_first:
        col.drop()
    # ensure index on id
    try:
        col.create_index("id", unique=True)
    except Exception:
        pass

    conn = sqlite3.connect(sqlite_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT " + ",".join(FIELDS) + " FROM book")
        count = 0
        batch: list[Dict[str, Any]] = []
        for row in iter_rows(cur):
            doc = normalize_row(row)
            batch.append(doc)
            if len(batch) >= 1000:
                # upsert by id
                for d in batch:
                    col.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
                count += len(batch)
                batch.clear()
        if batch:
            for d in batch:
                col.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            count += len(batch)
        return count
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> None:
    ap = argparse.ArgumentParser(description="Import SQLite book DB into MongoDB collection")
    ap.add_argument("--sqlite", required=False, default=os.path.join("bookstore", "fe", "data", "book.db"), help="Path to SQLite book.db or book_lx.db")
    ap.add_argument("--collection", required=False, default="bookdb_small", help="Target Mongo collection (bookdb_small|bookdb_large|...) ")
    ap.add_argument("--drop-first", action="store_true", help="Drop target collection before import")
    args = ap.parse_args()

    total = import_sqlite(args.sqlite, args.collection, drop_first=args.drop_first)
    print(f"Imported {total} rows into '{args.collection}' from '{args.sqlite}'")


if __name__ == "__main__":
    main()
