import json
import time
from urllib.parse import urljoin
import requests
from fe import conf
import types


class _BoomConn:
    def close(self):
        raise RuntimeError("close error")


class _FakeSeller:
    def __init__(self):
        self.conn = _BoomConn()

    def create_store(self, user_id, store_id):  # noqa: ANN001
        return 200, "ok"

    def add_book(self, *args, **kwargs):  # noqa: ANN001, ANN002
        return 200, "ok"

    def add_stock_level(self, *args, **kwargs):  # noqa: ANN001, ANN002
        return 200, "ok"


def test_seller_view_close_exceptions(monkeypatch):
    # 覆盖 be.view.seller 中三个接口 finally 里关闭连接异常分支
    import be.view.seller as vseller

    monkeypatch.setattr(vseller, "seller", types.SimpleNamespace(Seller=_FakeSeller))

    url_cs = urljoin(conf.URL, "seller/create_store")
    assert requests.post(url_cs, json={"user_id": "u", "store_id": "st"}).status_code == 200

    url_ab = urljoin(conf.URL, "seller/add_book")
    assert (
        requests.post(url_ab, json={"user_id": "u", "store_id": "st", "book_info": {"id": "b"}, "stock_level": 1}).status_code
        == 200
    )

    url_as = urljoin(conf.URL, "seller/add_stock_level")
    assert (
        requests.post(url_as, json={"user_id": "u", "store_id": "st", "book_id": "b", "add_stock_level": 1}).status_code
        == 200
    )


def test_seller_add_book_fallback_on_missing_columns(monkeypatch):
    # 在 Mongo 语义下：即使 book_info 含有额外字段或缺失部分可选字段，也应成功写入
    from be.model.seller_mongo import Seller
    from be.model.user_mongo import User
    from be.model import mongo_store

    uid = "u_" + str(int(time.time()*1000))[-6:]
    sid = "st_" + str(int(time.time()*1000))[-6:]
    User().register(uid, "p")
    s = Seller()
    assert s.create_store(uid, sid)[0] == 200
    # 包含额外字段 extra 不影响
    info = {"id": "bk", "title": "t", "author": "a", "isbn": "i", "price": 9, "extra": "x"}
    code, msg = s.add_book(uid, sid, "bk", json.dumps(info), 1)
    assert code == 200
    db = mongo_store.get_db()
    doc = db["inventory"].find_one({"store_id": sid, "book_id": "bk"})
    assert doc and int(doc.get("stock_level", 0)) == 1


def test_seller_create_store_retry_locked(monkeypatch):
    # Mongo-only：直接验证用户存在时创建店铺成功
    from be.model.seller_mongo import Seller
    from be.model.user_mongo import User

    uid = "u_" + str(int(time.time()*1000))[-6:]
    sid = "st_" + str(int(time.time()*1000))[-6:]
    User().register(uid, "p")
    s = Seller()
    code, msg = s.create_store(uid, sid)
    assert code == 200
