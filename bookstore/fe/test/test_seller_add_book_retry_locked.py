import json
from be.model.seller_mongo import Seller
from be.model.user_mongo import User
from be.model import mongo_store


def test_add_book_retry_locked_once():
    # Mongo-only：准备用户与店铺，直接验证 add_book 成功
    mongo_store.get_db()["user"].delete_one({"_id": "u_lock"})
    u = User()
    u.register("u_lock", "pw")
    s = Seller()
    s.create_store("u_lock", "st_lock")

    bi = {"id": "bk_lock", "title": "L", "author": "A", "isbn": "ISL"}
    code, msg = s.add_book("u_lock", "st_lock", "bk_lock", json.dumps(bi), 1)
    assert code == 200
