import json
import time
from typing import Tuple

from be.model import error
from be.model import db_conn
from be.model import mongo_store
from pymongo.errors import DuplicateKeyError, PyMongoError


class Seller(db_conn.DBConn):
    def __init__(self):
        # SQLite legacy removed; keep base init for compatibility
        db_conn.DBConn.__init__(self)
        self.mongo_db = mongo_store.get_db()
        self.col_users = self.mongo_db["user"]
        self.col_stores = self.mongo_db["stores"]
        self.col_inventory = self.mongo_db["inventory"]
        self.col_orders = self.mongo_db["orders"]
        self.col_order_details = self.mongo_db["order_details"]
        self.col_order_status = self.mongo_db["order_status"]

    # -------- helpers (Mongo-backed existence checks) --------
    def _user_exists(self, user_id: str) -> bool:
        return self.col_users.find_one({"_id": user_id}, {"_id": 1}) is not None

    def _store_exists(self, store_id: str) -> bool:
        return self.col_stores.find_one({"_id": store_id}, {"_id": 1}) is not None

    def _book_exists(self, store_id: str, book_id: str) -> bool:
        return (
            self.col_inventory.find_one(
                {"store_id": store_id, "book_id": book_id}, {"_id": 1}
            )
            is not None
        )

    # -------- APIs --------
    def create_store(self, user_id: str, store_id: str) -> Tuple[int, str]:
        try:
            if not self._user_exists(user_id):
                return error.error_non_exist_user_id(user_id)
            if self._store_exists(store_id):
                return error.error_exist_store_id(store_id)

            # Primary write: Mongo
            self.col_stores.insert_one({"_id": store_id, "owner_id": user_id})
            # SQLite mirroring removed
        except DuplicateKeyError:
            return error.error_exist_store_id(store_id)
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"

    def add_book(
        self,
        user_id: str,
        store_id: str,
        book_id: str,
        book_json_str: str,
        stock_level: int,
    ) -> Tuple[int, str]:
        try:
            # Normalize types
            try:
                stock_level = int(stock_level)
            except Exception:
                stock_level = 0

            # Load info for redundancy fields
            try:
                if isinstance(book_json_str, dict):
                    bi = book_json_str
                elif isinstance(book_json_str, str):
                    bi = json.loads(book_json_str) if book_json_str else {}
                else:
                    bi = {}
            except Exception:
                bi = {}

            title = bi.get("title")
            author = bi.get("author")
            isbn = bi.get("isbn")

            def _to_int(v):
                try:
                    if v is None:
                        return None
                    return int(v)
                except Exception:
                    return None

            pub_year = _to_int(bi.get("pub_year"))
            pages = _to_int(bi.get("pages"))
            price = _to_int(bi.get("price"))

            # Build a text blob for full-text index (tags/content/book_intro/catalog/publisher etc.)
            try:
                tags_val = bi.get("tags")
                if isinstance(tags_val, list):
                    tags_text = " ".join(str(x) for x in tags_val)
                else:
                    tags_text = str(tags_val or "")
                content_text = " ".join(
                    str(x)
                    for x in [
                        bi.get("content"),
                        bi.get("book_intro"),
                        bi.get("catalog"),
                        bi.get("publisher"),
                        bi.get("original_title"),
                        bi.get("translator"),
                    ]
                    if x
                )
            except Exception:
                tags_text = ""
                content_text = ""
            text_blob = " ".join(
                str(x) for x in [title, author, isbn, tags_text, content_text] if x
            )

            if not self._user_exists(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self._store_exists(store_id):
                return error.error_non_exist_store_id(store_id)
            if self._book_exists(store_id, book_id):
                return error.error_exist_book_id(book_id)

            # Primary write: Mongo inventory
            self.col_inventory.insert_one(
                {
                    "store_id": store_id,
                    "book_id": book_id,
                    "book_info": book_json_str,
                    "stock_level": stock_level,
                    "title": title,
                    "author": author,
                    "isbn": isbn,
                    "pub_year": pub_year,
                    "pages": pages,
                    "price": price,
                    "text_blob": text_blob,
                }
            )

            # SQLite mirroring removed
        except DuplicateKeyError:
            return error.error_exist_book_id(book_id)
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"

    def add_stock_level(
        self, user_id: str, store_id: str, book_id: str, add_stock_level: int
    ) -> Tuple[int, str]:
        try:
            try:
                add_stock_level = int(add_stock_level)
            except Exception:
                add_stock_level = 0

            if not self._user_exists(user_id):
                return error.error_non_exist_user_id(user_id)
            if not self._store_exists(store_id):
                return error.error_non_exist_store_id(store_id)
            if not self._book_exists(store_id, book_id):
                return error.error_non_exist_book_id(book_id)

            # Primary write: Mongo atomic increment
            res = self.col_inventory.update_one(
                {"store_id": store_id, "book_id": book_id},
                {"$inc": {"stock_level": add_stock_level}},
            )
            if res.matched_count == 0:
                return error.error_non_exist_book_id(book_id)

            # SQLite mirroring removed
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"

    def send_books(self, user_id: str, order_id: str) -> Tuple[int, str]:
        """Ship books for a paid order (Mongo-only)."""
        try:
            # Validate order exists and was paid
            paid_doc = next(
                iter(
                    self.col_order_status
                    .find({"order_id": order_id, "status": "paid"})
                    .sort([( "ts", -1)])
                    .limit(1)
                ),
                None,
            )
            if not paid_doc:
                return error.error_invalid_order_id(order_id)
            store_id = paid_doc.get("store_id")
            if not store_id:
                return error.error_invalid_order_id(order_id)

            # Authorization: only store owner can ship
            store = self.col_stores.find_one({"_id": store_id}, {"owner_id": 1})
            if not store:
                return error.error_non_exist_store_id(store_id)
            if store.get("owner_id") != user_id:
                return error.error_authorization_fail()

            # Check latest status
            last = next(
                iter(self.col_order_status.find({"order_id": order_id}).sort([( "ts", -1)]).limit(1)),
                None,
            )
            if last and last.get("status") in ("received", "canceled", "timed_out"):
                return 200, "ok"
            if last and last.get("status") not in ("paid", "shipped"):
                return error.error_authorization_fail()

            # Append shipped in Mongo
            shipped_ts = int(time.time() * 1000)
            self.col_order_status.insert_one(
                {
                    "order_id": order_id,
                    "status": "shipped",
                    "ts": shipped_ts,
                    "user_id": user_id,
                    "store_id": store_id,
                }
            )
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"
