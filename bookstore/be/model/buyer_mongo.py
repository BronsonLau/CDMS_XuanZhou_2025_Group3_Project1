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

    def _lazy_timeout_check_mongo(self, order_id: str):
        doc = self.col_orders.find_one({"_id": order_id}, {"created_ts": 1, "user_id": 1, "store_id": 1})
        if not doc:
            return False
        # created_ts 在 new_order 中以毫秒写入，这里统一使用毫秒计算超时
        created_ts_ms = int(doc.get("created_ts", int(time.time() * 1000)))
        now_ms = int(time.time() * 1000)
        if now_ms - created_ts_ms > self.ORDER_TIMEOUT_SECONDS * 1000:
            # Append timed_out if not already a terminal state
            latest = self.col_order_status.find({"order_id": order_id}).sort([("ts", -1)]).limit(1)
            last = next(iter(latest), None)
            if not last or last.get("status") not in ("timed_out", "canceled", "paid"):
                self.col_order_status.insert_one(
                    {
                        "order_id": order_id,
                        "status": "timed_out",
                        "ts": int(time.time() * 1000),
                        "user_id": doc.get("user_id"),
                        "store_id": doc.get("store_id"),
                    }
                )
                # SQLite mirror removed
            return True
        return False

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

    # SQLite helpers removed

    def receive_books(self, user_id: str, order_id: str):
        try:
            # Mongo-first: use order_status in MongoDB as source of truth
            last_doc = next(
                iter(self.col_order_status.find({"order_id": order_id}).sort([("ts", -1)]).limit(1)),
                None,
            )
            if not last_doc:
                return error.error_invalid_order_id(order_id)

            last_status = last_doc.get("status")
            if last_status in ("canceled", "timed_out"):
                return error.error_order_not_active()
            if last_status not in ("shipped", "receiving"):
                return error.error_order_not_shipped()

            # Authorization: ensure the paid record belongs to this user
            paid_doc = next(
                iter(
                    self.col_order_status
                    .find({"order_id": order_id, "status": "paid"})
                    .sort([("ts", -1)])
                    .limit(1)
                ),
                None,
            )
            if not paid_doc or paid_doc.get("user_id") != user_id:
                return error.error_authorization_fail()

            # Append received in Mongo
            received_ts = int(time.time() * 1000)
            store_id = last_doc.get("store_id") or paid_doc.get("store_id")
            try:
                self.col_order_status.insert_one(
                    {
                        "order_id": order_id,
                        "status": "received",
                        "ts": received_ts,
                        "user_id": user_id,
                        "store_id": store_id,
                    }
                )
            except Exception:
                # Even if insert fails, keep SQLite mirror attempt below
                pass

            # SQLite mirror removed

        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"

    def cancel_order(self, user_id: str, order_id: str):
        try:
            # Mongo-only logic
            last_doc = next(
                iter(self.col_order_status.find({"order_id": order_id}).sort([("ts", -1)]).limit(1)),
                None,
            )
            if not last_doc:
                return error.error_invalid_order_id(order_id)
            last_status = last_doc.get("status")
            if last_status == "paid":
                return error.error_order_already_paid()
            if last_status in ("canceled",):
                return 200, "ok"

            # Authorization: only creator can cancel before payment
            ord_doc = self.col_orders.find_one({"_id": order_id}, {"user_id": 1})
            if ord_doc is None and last_status not in ("timed_out",):
                return error.error_invalid_order_id(order_id)
            if ord_doc is not None and ord_doc.get("user_id") != user_id:
                return error.error_authorization_fail()

            # Append canceled
            # 统一使用毫秒时间戳
            self.col_order_status.insert_one(
                {"order_id": order_id, "status": "canceled", "ts": int(time.time() * 1000), "user_id": user_id}
            )
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"

    # -------- history / query --------
    def list_orders(
        self,
        user_id: str,
        page: int = 1,
        size: int = 20,
        status: Optional[str] = None,
    ) -> Tuple[int, str, List[Dict[str, Any]]]:
        try:
            page = max(1, int(page or 1))
            size = max(1, int(size or 20))
            skip = (page - 1) * size

            match: Dict[str, Any] = {"user_id": user_id}
            if status:
                match["status"] = status

            pipeline = [
                {"$match": match},
                {"$sort": {"order_id": 1, "ts": -1}},
                {
                    "$group": {
                        "_id": "$order_id",
                        "order_id": {"$first": "$order_id"},
                        "last_status": {"$first": "$status"},
                        "last_ts": {"$first": "$ts"},
                        "store_id": {"$first": "$store_id"},
                    }
                },
                {"$sort": {"last_ts": -1}},
                {"$skip": int(skip)},
                {"$limit": int(size)},
            ]
            rows = list(self.col_order_status.aggregate(pipeline))
            results: List[Dict[str, Any]] = []
            for r in rows:
                results.append(
                    {
                        "order_id": r.get("order_id"),
                        "status": r.get("last_status"),
                        "ts": int(r.get("last_ts", 0)),
                        "store_id": r.get("store_id"),
                    }
                )
            return 200, "ok", results
        except PyMongoError as e:
            return 528, f"{e}", []
        except BaseException as e:
            return 530, f"{e}", []
