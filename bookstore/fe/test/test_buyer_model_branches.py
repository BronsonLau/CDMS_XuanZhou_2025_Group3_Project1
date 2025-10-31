import uuid
from be.model import mongo_store
from be.model.buyer_mongo import Buyer


def _seed_user(db, user_id: str, password: str, balance: int = 0):
    db["user"].update_one({"_id": user_id}, {"$set": {"password": password, "balance": int(balance)}}, upsert=True)


def _seed_store_book(db, store_id: str, owner_id: str, book_id: str, stock: int, price: int = 100):
    db["stores"].update_one({"_id": store_id}, {"$set": {"owner_id": owner_id}}, upsert=True)
    db["inventory"].update_one(
        {"store_id": store_id, "book_id": book_id},
        {"$set": {"book_info": "{\\\"price\\\": %d}" % price, "stock_level": int(stock), "price": int(price)}},
        upsert=True,
    )


def _create_order(db, buyer_id: str, store_id: str, book_id: str, count: int) -> str:
    b = Buyer()
    code, msg, order_id = b.new_order(buyer_id, store_id, [(book_id, count)])
    assert code == 200
    return order_id


def test_payment_wrong_password_and_insufficient_update_rowcount():
    db = mongo_store.get_db()
    buyer_id = f"ub_{uuid.uuid4().hex[:6]}"
    seller_id = f"us_{uuid.uuid4().hex[:6]}"
    store_id = f"st_{uuid.uuid4().hex[:6]}"
    book_id = "bk_x"
    _seed_user(db, buyer_id, "p1", balance=100)
    _seed_user(db, seller_id, "ps", balance=0)
    _seed_store_book(db, store_id, seller_id, book_id, stock=10, price=60)

    b = Buyer()
    order_id = _create_order(db, buyer_id, store_id, book_id, 1)
    # 密码错误
    assert b.payment(buyer_id, "wrong", order_id)[0] != 200

    # 余额不足：提高订单数量且确保明细单价为 60，使总价超过余额(100) -> 2*60=120
    db["order_details"].update_one({"order_id": order_id, "book_id": book_id}, {"$set": {"count": 2, "price": 60}})
    code, _ = b.payment(buyer_id, "p1", order_id)
    assert code != 200


def test_payment_missing_seller_user_and_inventory_recheck_fail():
    db = mongo_store.get_db()
    buyer_id = f"ub_{uuid.uuid4().hex[:6]}"
    store_id = f"st_{uuid.uuid4().hex[:6]}"
    book_id = "bk_y"
    _seed_user(db, buyer_id, "p1", balance=10000)
    # 先写入卖家与 stores，保证下单成功
    seller_id0 = f"us_{uuid.uuid4().hex[:6]}"
    _seed_user(db, seller_id0, "ps", balance=0)
    _seed_store_book(db, store_id, seller_id0, book_id, stock=10, price=10)

    b = Buyer()
    order_id = _create_order(db, buyer_id, store_id, book_id, 1)
    # 删除 stores，制造支付阶段找不到卖家
    db["stores"].delete_one({"_id": store_id})
    assert b.payment(buyer_id, "p1", order_id)[0] != 200

    # 修复卖家，但让库存复检失败（下单后改成 0）
    seller_id = f"us_{uuid.uuid4().hex[:6]}"
    _seed_user(db, seller_id, "ps", balance=0)
    db["stores"].update_one({"_id": store_id}, {"$set": {"owner_id": seller_id}}, upsert=True)
    db["inventory"].update_one({"store_id": store_id, "book_id": book_id}, {"$set": {"stock_level": 0}})
    assert b.payment(buyer_id, "p1", order_id)[0] != 200


def test_payment_lazy_timeout_path():
    db = mongo_store.get_db()
    buyer_id = f"ub_{uuid.uuid4().hex[:6]}"
    seller_id = f"us_{uuid.uuid4().hex[:6]}"
    store_id = f"st_{uuid.uuid4().hex[:6]}"
    book_id = "bk_t"
    _seed_user(db, buyer_id, "p1", balance=10000)
    _seed_user(db, seller_id, "ps", balance=0)
    _seed_store_book(db, store_id, seller_id, book_id, stock=10, price=10)

    b = Buyer()
    code, msg, order_id = b.new_order(buyer_id, store_id, [(book_id, 1)])
    assert code == 200
    # 直接把 created 状态的 ts 回写为过去，触发惰性超时判断
    db["orders"].update_one({"_id": order_id}, {"$set": {"created_ts": 1}})
    # 支付前将其标记为超时，payment 应返回不可支付
    assert b.payment(buyer_id, "p1", order_id)[0] != 200
