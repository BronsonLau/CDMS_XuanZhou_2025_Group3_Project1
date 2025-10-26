import jwt
import time
import logging
import random
import threading
from typing import Tuple

from be.model import error
from be.model import db_conn
from be.model import mongo_store
from pymongo.errors import DuplicateKeyError, PyMongoError


def jwt_encode(user_id: str, terminal: str) -> str:
    encoded = jwt.encode(
        {"user_id": user_id, "terminal": terminal, "timestamp": time.time()},
        key=user_id,
        algorithm="HS256",
    )
    return encoded if isinstance(encoded, str) else encoded.decode("utf-8")


def jwt_decode(encoded_token, user_id: str) -> str:
    return jwt.decode(encoded_token, key=user_id, algorithms=["HS256"])  # type: ignore[arg-type]


class User(db_conn.DBConn):
    token_lifetime: int = 3600
    _register_lock = threading.Lock()

    def __init__(self):
        db_conn.DBConn.__init__(self)
        self.mongo_db = mongo_store.get_db()
        mongo_store.ensure_indexes(self.mongo_db)
        self.col_users = self.mongo_db["user"]

    def __check_token(self, user_id, db_token, token) -> bool:
        try:
            if db_token != token:
                return False
            jwt_text = jwt_decode(encoded_token=token, user_id=user_id)
            ts = jwt_text["timestamp"]
            if ts is not None:
                now = time.time()
                if self.token_lifetime > now - ts >= 0:
                    return True
        except jwt.exceptions.InvalidSignatureError as e:
            logging.error(str(e))
            return False

    def register(self, user_id: str, password: str):
        attempts = 20
        last_err: Exception | None = None
        while attempts > 0:
            try:
                with User._register_lock:
                    terminal = f"terminal_{time.time()}"
                    token = jwt_encode(user_id, terminal)
                    self.col_users.insert_one(
                        {
                            "_id": user_id,
                            "password": password,
                            "balance": 0,
                            "token": token,
                            "terminal": terminal,
                        }
                    )
                    # SQLite mirroring removed
                return 200, "ok"
            except DuplicateKeyError:
                return error.error_exist_user_id(user_id)
            except PyMongoError as e:
                last_err = e
                attempts -= 1
                time.sleep(0.05 + random.uniform(0, 0.05))
                continue
            except BaseException as e:
                logging.error(f"register exception: {e}")
                return 528, f"{e}"
        if last_err is not None:
            return 528, f"{last_err}"
        return 528, "register failed"

    def check_token(self, user_id: str, token: str) -> Tuple[int, str]:
        row = self.col_users.find_one({"_id": user_id}, {"token": 1})
        if not row:
            return error.error_authorization_fail()
        db_token = row.get("token", "")
        if not self.__check_token(user_id, db_token, token):
            return error.error_authorization_fail()
        return 200, "ok"

    def check_password(self, user_id: str, password: str) -> Tuple[int, str]:
        row = self.col_users.find_one({"_id": user_id}, {"password": 1})
        if not row:
            return error.error_authorization_fail()
        if password != row.get("password"):
            return error.error_authorization_fail()
        return 200, "ok"

    def login(self, user_id: str, password: str, terminal: str) -> Tuple[int, str, str]:
        token = ""
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message, ""

            token = jwt_encode(user_id, terminal)
            res = self.col_users.update_one(
                {"_id": user_id}, {"$set": {"token": token, "terminal": terminal}}
            )
            if res.matched_count == 0:
                return error.error_authorization_fail() + ("",)
            # SQLite mirroring removed
        except PyMongoError as e:
            return 528, f"{e}", ""
        except BaseException as e:
            return 530, f"{e}", ""
        return 200, "ok", token

    def logout(self, user_id: str, token: str) -> Tuple[int, str]:
        try:
            code, message = self.check_token(user_id, token)
            if code != 200:
                return code, message

            terminal = f"terminal_{time.time()}"
            dummy_token = jwt_encode(user_id, terminal)

            res = self.col_users.update_one(
                {"_id": user_id}, {"$set": {"token": dummy_token, "terminal": terminal}}
            )
            if res.matched_count == 0:
                return error.error_authorization_fail()
            # SQLite mirroring removed
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"

    def unregister(self, user_id: str, password: str) -> Tuple[int, str]:
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message

            res = self.col_users.delete_one({"_id": user_id})
            if res.deleted_count != 1:
                return error.error_authorization_fail()
            # SQLite mirroring removed
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"

    def change_password(
        self, user_id: str, old_password: str, new_password: str
    ) -> Tuple[int, str]:
        try:
            code, message = self.check_password(user_id, old_password)
            if code != 200:
                return code, message

            terminal = f"terminal_{time.time()}"
            token = jwt_encode(user_id, terminal)
            res = self.col_users.update_one(
                {"_id": user_id},
                {"$set": {"password": new_password, "token": token, "terminal": terminal}},
            )
            if res.matched_count == 0:
                return error.error_authorization_fail()
            # SQLite mirroring removed
        except PyMongoError as e:
            return 528, f"{e}"
        except BaseException as e:
            return 530, f"{e}"
        return 200, "ok"
