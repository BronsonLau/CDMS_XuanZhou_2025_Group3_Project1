from be.model.seller_mongo import Seller
from be.model.user_mongo import User
from be.model import mongo_store


def test_add_stock_level_retry_locked():
    # 基础数据（Mongo）
    db = mongo_store.get_db()
    db["user"].delete_one({"_id": "uX"})
    u = User()
    u.register("uX", "p")
    s = Seller()
    s.create_store("uX", "sX")
    # 先放一条库存
    db["inventory"].delete_one({"store_id": "sX", "book_id": "bX"})
    db["inventory"].insert_one({
        "store_id": "sX",
        "book_id": "bX",
        "book_info": "{}",
        "stock_level": 1,
        "title": None,
        "author": None,
        "isbn": None,
        "pub_year": None,
        "pages": None,
        "price": None,
    })

    code, _ = s.add_stock_level("uX", "sX", "bX", 3)
    assert code == 200
    # 验证库存增加（Mongo）
    row = db["inventory"].find_one({"store_id": "sX", "book_id": "bX"}, {"stock_level": 1})
    assert row and row.get("stock_level") == 4
