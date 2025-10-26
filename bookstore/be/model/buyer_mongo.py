import json
import time
import uuid
from typing import List, Tuple

from be.model import db_conn
from be.model import error
from be.model import mongo_store
from pymongo.errors import PyMongoError
from typing import Optional, Dict, Any


class Buyer(db_conn.DBConn):
    """Buyer operations backed by MongoDB only (SQLite legacy removed)."""

    ORDER_TIMEOUT_SECONDS = 30 * 60

    def __init__(self):
        db_conn.DBConn.__init__(self)
        self.mongo_db = mongo_store.get_db()
        self.col_users = self.mongo_db["user"]
        self.col_stores = self.mongo_db["stores"]
        self.col_inventory = self.mongo_db["inventory"]
        self.col_orders = self.mongo_db["orders"]
        self.col_order_details = self.mongo_db["order_details"]
        self.col_order_status = self.mongo_db["order_status"]

    # -------- helpers --------
    def _user_exists(self, user_id: str) -> bool:
        return self.col_users.find_one({"_id": user_id}, {"_id": 1}) is not None

    def _store_exists(self, store_id: str) -> bool:
        return self.col_stores.find_one({"_id": store_id}, {"_id": 1}) is not None

    def _fetch_inventory(self, store_id: str, book_id: str):
        return self.col_inventory.find_one(
            {"store_id": store_id, "book_id": book_id}, {"stock_level": 1, "book_info": 1, "price": 1}
        )

    # SQLite mirror removed

    def new_order(self, user_id: str, store_id: str, id_and_count: List[Tuple[str, int]]):
        order_id = ""
        try:
            if not self._user_exists(user_id):
                return error.error_non_exist_user_id(user_id) + (order_id,)
            if not self._store_exists(store_id):
                return error.error_non_exist_store_id(store_id) + (order_id,)

            # Validate items and prepare details
            details_docs = []
            for book_id, count in id_and_count:
                doc = self._fetch_inventory(store_id, book_id)
                if doc is None:
                    return error.error_non_exist_book_id(book_id) + (order_id,)
                stock = int(doc.get("stock_level", 0))
                if stock < int(count):
                    return error.error_stock_level_low(book_id) + (order_id,)
                # Use redundant price if present, fallback to JSON
                price = doc.get("price")
                if price is None:
                    try:
                        price = int(json.loads(doc.get("book_info") or "{}").get("price", 0))
                    except Exception:
                        price = 0
                details_docs.append({"book_id": book_id, "count": int(count), "price": int(price)})
                # SQLite details removed

            uid = f"{user_id}_{store_id}_{uuid.uuid1()}"
            order_id = uid

            # Primary writes in Mongo
            created_ts = int(time.time() * 1000)  # Use milliseconds for better precision
            self.col_orders.insert_one(
                {"_id": uid, "user_id": user_id, "store_id": store_id, "created_ts": created_ts}
            )
            for d in details_docs:
                ddoc = {"order_id": uid} | d
                self.col_order_details.insert_one(ddoc)
            self.col_order_status.insert_one(
                {"order_id": uid, "status": "created", "ts": created_ts, "user_id": user_id, "store_id": store_id}
            )

            # SQLite mirroring removed
        except PyMongoError as e:
            return 528, f"{e}", ""
        except BaseException as e:
            return 530, f"{e}", ""
        return 200, "ok", order_id

    def payment(self, user_id: str, password: str, order_id: str):
        try:
            # Validate order owner
            o = self.col_orders.find_one({"_id": order_id}, {"user_id": 1, "store_id": 1})
            if not o:
                return error.error_invalid_order_id(order_id)
            if o.get("user_id") != user_id:
                return error.error_authorization_fail()

            store_id = o.get("store_id")

            # Timeout check
            if self._lazy_timeout_check_mongo(order_id):
                return error.error_order_not_active()
            # Also check latest status
            last = next(
                iter(self.col_order_status.find({"order_id": order_id}).sort([("ts", -1)]).limit(1)),
                None,
            )
            if last and last.get("status") in ("timed_out", "canceled"):
                return error.error_order_not_active()

            # Password & balance
            u = self.col_users.find_one({"_id": user_id}, {"password": 1, "balance": 1})
            if not u:
                return error.error_non_exist_user_id(user_id)
            if u.get("password") != password:
                return error.error_authorization_fail()
            buyer_balance = int(u.get("balance", 0))

            # Seller id from stores (Mongo)
            s = self.col_stores.find_one({"_id": store_id}, {"owner_id": 1})
            if not s:
                return error.error_non_exist_store_id(store_id)
            seller_id = s.get("owner_id")
            # SQLite user_store check removed

            # Sum total and validate inventory
            total_price = 0
            items = list(self.col_order_details.find({"order_id": order_id}, {"book_id": 1, "count": 1, "price": 1}))
            for it in items:
                total_price += int(it.get("price", 0)) * int(it.get("count", 0))
            if buyer_balance < total_price:
                return error.error_not_sufficient_funds(order_id)

            # Re-check and deduct inventory in Mongo atomically per item
            for it in items:
                book_id = it["book_id"]
                count = int(it["count"])
                res = self.col_inventory.update_one(
                    {"store_id": store_id, "book_id": book_id, "stock_level": {"$gte": count}},
                    {"$inc": {"stock_level": -count}},
                )
                if res.modified_count == 0:
                    return error.error_stock_level_low(book_id)

                # SQLite mirror removed

            # Transfer funds in Mongo
            res = self.col_users.update_one(
                {"_id": user_id, "balance": {"$gte": total_price}}, {"$inc": {"balance": -int(total_price)}}
            )
            if res.modified_count == 0:
                return error.error_not_sufficient_funds(order_id)
            self.col_users.update_one({"_id": seller_id}, {"$inc": {"balance": int(total_price)}})

            # SQLite balance mirror removed

            # Mark paid in both stores (ensure unique timestamp)
            import time
            paid_ts = int(time.time() * 1000)  # Use milliseconds for better precision
            self.col_order_status.insert_one(
                {"order_id": order_id, "status": "paid", "ts": paid_ts, "user_id": user_id, "store_id": store_id}
            )
            # SQLite status mirror removed

            # Remove order docs to prevent repeat pay
            self.col_order_details.delete_many({"order_id": order_id})
            self.col_orders.delete_one({"_id": order_id})

            # SQLite cleanup removed
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"

    def add_funds(self, user_id, password, add_value):
        try:
            row = self.col_users.find_one({"_id": user_id}, {"password": 1})
            if not row:
                return error.error_authorization_fail()
            if row.get("password") != password:
                return error.error_authorization_fail()

            self.col_users.update_one({"_id": user_id}, {"$inc": {"balance": int(add_value)}})

            # SQLite mirror removed
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"
