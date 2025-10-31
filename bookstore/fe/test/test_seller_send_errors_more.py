from be.model.seller_mongo import Seller
from be.model import mongo_store
from pymongo.errors import PyMongoError


def test_send_books_invalid_order_id():
    s = Seller()
    code, msg = s.send_books(user_id="u_x", order_id="not_exist")
    assert code != 200


def test_send_books_owner_none():
    # 构造一条 paid 状态，但 stores 中无该 store_id
    db = mongo_store.get_db()
    order_id = "ord_no_owner"
    db["order_status"].insert_one({
        "order_id": order_id,
        "status": "paid",
        "ts": 1,
        "user_id": "buyer",
        "store_id": "st_no_owner",
    })
    s = Seller()
    code, msg = s.send_books(user_id="seller_x", order_id=order_id)
    assert code != 200


def test_send_books_pymongo_and_base_exceptions(monkeypatch):
    s = Seller()

    # 让底层查询抛 PyMongoError -> 528
    monkeypatch.setattr(s.col_order_status, "find", lambda *a, **k: (_ for _ in ()).throw(PyMongoError("db down")))
    code, msg = s.send_books(user_id="u", order_id="o")
    assert code == 528

    # 让底层查询抛 RuntimeError -> 530
    def boom(*a, **k):
        raise RuntimeError("boom")

    s2 = Seller()
    monkeypatch.setattr(s2.col_order_status, "find", boom)
    code2, msg2 = s2.send_books(user_id="u", order_id="o")
    assert code2 == 530


def test_send_books_latest_status_invalid_authorization_fail():
    # 构造：已存在 paid，但最新状态是 created（既非终态也非允许状态），应返回 401
    db = mongo_store.get_db()
    order_id = "ord_bad_latest"
    store_id = "st_bad"
    owner_id = "seller_bad"
    # 店主存在于 stores
    db["user"].update_one({"_id": owner_id}, {"$set": {"password": "p", "balance": 0}}, upsert=True)
    db["stores"].update_one({"_id": store_id}, {"$set": {"owner_id": owner_id}}, upsert=True)
    # 先写入 paid（确保第一关通过）
    db["order_status"].insert_one({
        "order_id": order_id,
        "status": "paid",
        "ts": 1,
        "user_id": "buyer",
        "store_id": store_id,
    })
    # 再写入 created 使其为最新状态（非法）
    db["order_status"].insert_one({
        "order_id": order_id,
        "status": "created",
        "ts": 2,
        "user_id": "buyer",
        "store_id": store_id,
    })

    s = Seller()
    code, msg = s.send_books(user_id=owner_id, order_id=order_id)
    assert code == 401
