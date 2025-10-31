import time
import json
import uuid
from fe import conf
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access.book import BookDB
import requests
from urllib.parse import urljoin


def test_ship_receive_flow():
    # 准备用户与店铺、书籍
    suffix = str(uuid.uuid4())[:8]
    seller_id = f"s_ship_{suffix}"
    buyer_id = f"b_ship_{suffix}"
    password = "pass"
    s = register_new_seller(seller_id, password)
    b = register_new_buyer(buyer_id, password)

    store_id = f"st_ship_{suffix}"
    assert s.create_store(store_id) == 200

    # 选一本书
    db = BookDB(large=False)
    books = db.get_book_info(0, 1)
    book = books[0]
    assert s.add_book(store_id, 10, book) == 200

    # 下单并支付
    code, order_id = b.new_order(store_id, [(book.id, 1)])
    assert code == 200
    assert b.add_funds(100000) == 200
    assert b.payment(order_id) == 200

    # 卖家发货
    assert s.send_books(order_id) == 200
    # 买家收货
    assert b.receive_books(order_id) == 200


def test_cancel_before_pay():
    suffix = str(uuid.uuid4())[:8]
    seller_id = f"s_cancel_{suffix}"
    buyer_id = f"b_cancel_{suffix}"
    password = "pass"
    s = register_new_seller(seller_id, password)
    b = register_new_buyer(buyer_id, password)
    store_id = f"st_cancel_{suffix}"
    assert s.create_store(store_id) == 200

    db = BookDB(large=False)
    book = db.get_book_info(0, 1)[0]
    assert s.add_book(store_id, 5, book) == 200

    code, order_id = b.new_order(store_id, [(book.id, 1)])
    assert code == 200

    # 未支付取消
    assert b.cancel_order(order_id) == 200
    # 再次取消为幂等
    assert b.cancel_order(order_id) == 200
    # 取消后支付应失败
    assert b.payment(order_id) != 200


def test_timeout_then_cancel():
    # 配置短超时时间
    url = urljoin(conf.URL, "admin/config")
    r = requests.post(url, json={"order_timeout_seconds": 1})
    assert r.status_code == 200

    suffix = str(uuid.uuid4())[:8]
    seller_id = f"s_to_{suffix}"
    buyer_id = f"b_to_{suffix}"
    password = "pass"
    s = register_new_seller(seller_id, password)
    b = register_new_buyer(buyer_id, password)
    store_id = f"st_to_{suffix}"
    assert s.create_store(store_id) == 200

    db = BookDB(large=False)
    book = db.get_book_info(0, 1)[0]
    assert s.add_book(store_id, 5, book) == 200

    code, order_id = b.new_order(store_id, [(book.id, 1)])
    assert code == 200

    # 等待超时
    time.sleep(2)

    # 超时后支付应失败
    assert b.payment(order_id) != 200
    # 可以取消
    assert b.cancel_order(order_id) == 200
