from pymongo.errors import PyMongoError
from be.model.buyer_mongo import Buyer


def test_buyer_new_order_pymongo_error_returns_528(monkeypatch):
    b = Buyer()
    # 让用户存在性检查抛出 PyMongoError
    monkeypatch.setattr(b.col_users, "find_one", lambda *a, **k: (_ for _ in ()).throw(PyMongoError("boom")))
    code, msg, oid = b.new_order("u", "s", [("b", 1)])
    assert code == 528 and oid == ""


def test_buyer_payment_pymongo_error_returns_528(monkeypatch):
    b = Buyer()
    # 读取订单抛 PyMongoError
    monkeypatch.setattr(b.col_orders, "find_one", lambda *a, **k: (_ for _ in ()).throw(PyMongoError("boom")))
    code, msg = b.payment("u", "p", "o")
    assert code == 528


def test_buyer_add_funds_pymongo_error_returns_528(monkeypatch):
    b = Buyer()
    monkeypatch.setattr(b.col_users, "find_one", lambda *a, **k: (_ for _ in ()).throw(PyMongoError("boom")))
    code, msg = b.add_funds("u", "p", 1)
    assert code == 528


def test_buyer_receive_cancel_pymongo_error_returns_528(monkeypatch):
    b = Buyer()
    # receive_books: 查询状态抛异常
    class _Cur:
        def sort(self, *a, **k):
            return self

        def limit(self, *a, **k):
            return self

        def __iter__(self):
            raise PyMongoError("boom")

    monkeypatch.setattr(b.col_order_status, "find", lambda *a, **k: _Cur())
    assert b.receive_books("u", "o")[0] == 528

    # cancel_order: 同样依赖 order_status.find
    monkeypatch.setattr(b.col_order_status, "find", lambda *a, **k: _Cur())
    assert b.cancel_order("u", "o")[0] == 528


def test_buyer_add_funds_runtime_error_returns_530(monkeypatch):
    b = Buyer()
    monkeypatch.setattr(b.col_users, "find_one", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    code, msg = b.add_funds("u", "p", 1)
    assert code == 530
