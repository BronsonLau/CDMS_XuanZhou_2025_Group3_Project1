from be.model.seller_mongo import Seller
from be.model.user_mongo import User
from be.model import mongo_store


def test_add_book_fallback_to_base_columns():
    # Mongo-only: 用户/店铺 + add_book，验证写入成功
    db = mongo_store.get_db()
    uid = "uY"
    sid = "sY"
    bid = "bY"
    User().register(uid, "p")
    s = Seller()
    assert s.create_store(uid, sid)[0] == 200
    code, _ = s.add_book(uid, sid, bid, '{"title":"T","author":"A","isbn":"I","price":9}', 5)
    assert code == 200
    doc = db["inventory"].find_one({"store_id": sid, "book_id": bid})
    assert doc and int(doc.get("stock_level", 0)) == 5
