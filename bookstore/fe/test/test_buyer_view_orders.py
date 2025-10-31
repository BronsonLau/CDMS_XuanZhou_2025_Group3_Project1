import json
import requests
from urllib.parse import urljoin

from be.model.user_mongo import User
from be.model.seller_mongo import Seller
from be.model.buyer_mongo import Buyer
from fe import conf


def _seed_orders(n: int = 2):
    u = User()
    s = Seller()
    b = Buyer()
    buyer_id = "u_view_hist"
    seller_id = "u_view_seller"
    store_id = "st_view_1"
    book_id = "bk_view_1"

    # 注册/建店/上架
    u.register(buyer_id, "pw")
    u.register(seller_id, "pw")
    s.create_store(seller_id, store_id)
    book_info = {
        "id": book_id,
        "title": "Order Book",
        "author": "AU",
        "isbn": "9780000789",
        "price": 80,
        "pages": 120,
        "pub_year": 2024,
    }
    s.add_book(seller_id, store_id, book_id, json.dumps(book_info), 50)

    # 资金与下单
    b.add_funds(buyer_id, "pw", 100000)
    order_ids = []
    for _ in range(max(1, n)):
        code, msg, oid = b.new_order(buyer_id, store_id, [(book_id, 1)])
        assert code == 200 and oid
        order_ids.append(oid)
    return buyer_id, order_ids


def test_buyer_orders_view_returns_total_and_page_results():
    buyer_id, order_ids = _seed_orders(n=2)

    # 调用视图接口 /buyer/orders，分页 size=1，但 count 应反映总量（去重后的订单数）
    url = urljoin(conf.URL, "buyer/orders")
    r = requests.post(url, json={"user_id": buyer_id, "page": 1, "size": 1})
    assert r.status_code == 200
    data = r.json()
    assert data.get("count", 0) >= 2
    assert len(data.get("results", [])) == 1

    # 带 status 过滤：created（new_order 已写入该状态）
    r2 = requests.post(url, json={"user_id": buyer_id, "status": "created", "page": 1, "size": 5})
    assert r2.status_code == 200
    data2 = r2.json()
    assert data2.get("count", 0) >= 2
    assert all(item.get("status") == "created" for item in data2.get("results", []))


def test_buyer_orders_view_fallback_count(monkeypatch):
    # 有数据的前提下，强制统计阶段抛异常，触发兜底逻辑：count == len(results)
    buyer_id, _ = _seed_orders(n=1)

    # 自定义 Buyer 以在聚合统计时抛出异常
    import be.view.buyer as buyer_view
    import be.model.buyer_mongo as buyer_model

    class MockAgg:
        def aggregate(self, *args, **kwargs):
            raise RuntimeError("agg boom")

    class MockBuyer(buyer_model.Buyer):
        def __init__(self):
            super().__init__()

        def list_orders(self, *args, **kwargs):
            # 先按正常逻辑获取结果
            code, msg, results = super().list_orders(*args, **kwargs)
            # 然后将用于统计的集合替换为会抛异常的版本，以触发视图中的兜底
            self.col_order_status = MockAgg()
            return code, msg, results

    monkeypatch.setattr(buyer_view, "Buyer", MockBuyer, raising=True)

    url = urljoin(conf.URL, "buyer/orders")
    r = requests.post(url, json={"user_id": buyer_id, "page": 1, "size": 3})
    assert r.status_code == 200
    data = r.json()
    # 兜底：count 回退为当前页长度
    assert data.get("count") == len(data.get("results", []))


def _mk_ids(prefix: str):
    import time
    suffix = str(int(time.time() * 1000))
    return f"{prefix}_{suffix}"


def _seed_store_with_book(book_price: int = 80):
    u = User()
    s = Seller()
    buyer_id = _mk_ids("buyerv")
    seller_id = _mk_ids("sellerv")
    store_id = _mk_ids("storev")
    book_id = _mk_ids("bkv")
    u.register(buyer_id, "pw")
    u.register(seller_id, "pw")
    s.create_store(seller_id, store_id)
    book_info = {
        "id": book_id,
        "title": "V-Book",
        "author": "AU",
        "isbn": "9780000123",
        "price": book_price,
        "pages": 200,
        "pub_year": 2024,
    }
    s.add_book(seller_id, store_id, book_id, json.dumps(book_info), 100)
    return buyer_id, seller_id, store_id, book_id


def test_add_funds_view_success_and_wrong_password():
    buyer_id, _, _, _ = _seed_store_with_book()
    url = urljoin(conf.URL, "buyer/add_funds")
    # 错误密码
    r1 = requests.post(url, json={"user_id": buyer_id, "password": "wrong", "add_value": 100})
    assert r1.status_code == 401
    # 正确密码
    r2 = requests.post(url, json={"user_id": buyer_id, "password": "pw", "add_value": 1000})
    assert r2.status_code == 200


def test_new_order_and_cancel_flow():
    buyer_id, seller_id, store_id, book_id = _seed_store_with_book()

    # 下单（视图）
    new_order_url = urljoin(conf.URL, "buyer/new_order")
    r = requests.post(
        new_order_url,
        json={"user_id": buyer_id, "store_id": store_id, "books": [{"id": book_id, "count": 1}]},
    )
    assert r.status_code == 200
    order_id = r.json().get("order_id")
    assert order_id

    # 取消（视图）
    cancel_url = urljoin(conf.URL, "buyer/cancel_order")
    r2 = requests.post(cancel_url, json={"user_id": buyer_id, "order_id": order_id})
    assert r2.status_code == 200


def test_payment_auth_fail_then_success_then_cancel_after_paid():
    buyer_id, seller_id, store_id, book_id = _seed_store_with_book(book_price=50)
    other_user = _mk_ids("other")
    User().register(other_user, "pw")

    # 下单（视图）
    new_order_url = urljoin(conf.URL, "buyer/new_order")
    r = requests.post(
        new_order_url,
        json={"user_id": buyer_id, "store_id": store_id, "books": [{"id": book_id, "count": 2}]},
    )
    assert r.status_code == 200
    order_id = r.json().get("order_id")

    # 充值（视图）
    add_url = urljoin(conf.URL, "buyer/add_funds")
    r_add = requests.post(add_url, json={"user_id": buyer_id, "password": "pw", "add_value": 10000})
    assert r_add.status_code == 200

    # 使用另一用户试图支付（应鉴权失败）
    pay_url = urljoin(conf.URL, "buyer/payment")
    r_pay_fail = requests.post(pay_url, json={"user_id": other_user, "password": "pw", "order_id": order_id})
    assert r_pay_fail.status_code == 401

    # 正常支付
    r_pay_ok = requests.post(pay_url, json={"user_id": buyer_id, "password": "pw", "order_id": order_id})
    assert r_pay_ok.status_code == 200

    # 已支付后取消，应提示已支付
    cancel_url = urljoin(conf.URL, "buyer/cancel_order")
    r_cancel = requests.post(cancel_url, json={"user_id": buyer_id, "order_id": order_id})
    assert r_cancel.status_code == 531


def test_receive_books_not_shipped_both_before_and_after_pay():
    buyer_id, seller_id, store_id, book_id = _seed_store_with_book(book_price=30)

    # 下单
    new_order_url = urljoin(conf.URL, "buyer/new_order")
    r = requests.post(
        new_order_url,
        json={"user_id": buyer_id, "store_id": store_id, "books": [{"id": book_id, "count": 1}]},
    )
    order_id = r.json().get("order_id")

    # 未发货直接收货 -> 530
    recv_url = urljoin(conf.URL, "buyer/receive_book")
    r_recv1 = requests.post(recv_url, json={"user_id": buyer_id, "order_id": order_id})
    assert r_recv1.status_code == 530

    # 支付后仍未发货 -> 530
    add_url = urljoin(conf.URL, "buyer/add_funds")
    requests.post(add_url, json={"user_id": buyer_id, "password": "pw", "add_value": 10000})
    pay_url = urljoin(conf.URL, "buyer/payment")
    requests.post(pay_url, json={"user_id": buyer_id, "password": "pw", "order_id": order_id})
    r_recv2 = requests.post(recv_url, json={"user_id": buyer_id, "order_id": order_id})
    assert r_recv2.status_code == 530


def test_payment_wrong_password():
    buyer_id, seller_id, store_id, book_id = _seed_store_with_book(book_price=120)

    # 下单
    new_order_url = urljoin(conf.URL, "buyer/new_order")
    r = requests.post(
        new_order_url,
        json={"user_id": buyer_id, "store_id": store_id, "books": [{"id": book_id, "count": 1}]},
    )
    order_id = r.json().get("order_id")

    # 用错误密码支付 -> 401
    pay_url = urljoin(conf.URL, "buyer/payment")
    r_pay = requests.post(pay_url, json={"user_id": buyer_id, "password": "wrong", "order_id": order_id})
    assert r_pay.status_code == 401


def test_payment_insufficient_funds():
    buyer_id, seller_id, store_id, book_id = _seed_store_with_book(book_price=500)

    # 下单，合计 1000
    new_order_url = urljoin(conf.URL, "buyer/new_order")
    r = requests.post(
        new_order_url,
        json={"user_id": buyer_id, "store_id": store_id, "books": [{"id": book_id, "count": 2}]},
    )
    order_id = r.json().get("order_id")

    # 不充值直接支付 -> 519 资金不足
    pay_url = urljoin(conf.URL, "buyer/payment")
    r_pay = requests.post(pay_url, json={"user_id": buyer_id, "password": "pw", "order_id": order_id})
    assert r_pay.status_code == 519
