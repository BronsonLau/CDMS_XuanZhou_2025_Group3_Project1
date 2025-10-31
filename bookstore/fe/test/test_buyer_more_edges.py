from be.model.buyer_mongo import Buyer
from be.model import mongo_store


def test_cancel_order_already_paid():
    db = mongo_store.get_db()
    order_id = "ord_paid"
    # 最新状态设为 paid
    db["order_status"].insert_one({
        "order_id": order_id,
        "status": "paid",
        "ts": 10,
        "user_id": "buyer_x",
        "store_id": "st_x",
    })
    b = Buyer()
    code, msg = b.cancel_order("buyer_x", order_id)
    assert code == 531


def test_receive_books_not_shipped():
    db = mongo_store.get_db()
    order_id = "ord_not_shipped"
    # 最新状态设为 paid（非 shipped/receiving）
    db["order_status"].insert_one({
        "order_id": order_id,
        "status": "paid",
        "ts": 5,
        "user_id": "buyer_y",
        "store_id": "st_y",
    })
    b = Buyer()
    code, msg = b.receive_books("buyer_y", order_id)
    assert code == 530


def test_add_funds_wrong_password_and_nonexist_user():
    b = Buyer()
    # 不存在的用户：返回授权失败
    assert b.add_funds("no_user", "p", 10)[0] == 401

    # 创建一个用户，密码错误时也返回授权失败（Mongo）
    db = mongo_store.get_db()
    db["user"].update_one({"_id": "u1"}, {"$set": {"password": "p1", "balance": 0}}, upsert=True)
    assert b.add_funds("u1", "wrong", 10)[0] == 401
