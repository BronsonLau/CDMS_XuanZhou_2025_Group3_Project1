import json
from be.model.seller_mongo import Seller
from be.model.user_mongo import User
from be.model import mongo_store


def test_add_book_malformed_json_and_fallback():
    # 准备用户与店铺（Mongo）
    u = User()
    s = Seller()
    mongo_store.get_db()["user"].delete_one({"_id": "u_ut"})
    u.register("u_ut", "p")
    s.create_store("u_ut", "st_ut")

    # 传入非 JSON 字符串，内部会 except 后以空 dict 处理并尝试插入
    code, msg = s.add_book("u_ut", "st_ut", "bk_ut1", "{bad-json}", 1)
    assert code == 200

    # 再次插入相同 book_id，命中 exist 分支
    code, msg = s.add_book("u_ut", "st_ut", "bk_ut1", json.dumps({"id": "bk_ut1"}), 1)
    assert code == 516


def test_add_stock_level_errors():
    s = Seller()
    # 不存在的用户
    code, _ = s.add_stock_level("no_user", "st_ut2", "bk_x", 1)
    assert code == 511

    # 准备用户但无店铺（仅注册用户，不创建店铺）
    u = User()
    mongo_store.get_db()["user"].delete_one({"_id": "u_ut2"})
    u.register("u_ut2", "p")
    code, _ = s.add_stock_level("u_ut2", "no_store", "bk_x", 1)
    assert code == 513
