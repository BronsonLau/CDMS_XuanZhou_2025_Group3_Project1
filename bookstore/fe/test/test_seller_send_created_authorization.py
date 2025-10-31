import time
import requests
from urllib.parse import urljoin
from fe import conf
from be.model import mongo_store


def _api(path: str):
    return urljoin(conf.URL, path)


def test_send_books_latest_not_paid_or_shipped():
    # seller and buyer
    sid = "seller_xx"
    bid = "buyer_xx"
    st = "store_xx"
    book_id = "bk_send_auth"

    # register/login
    assert requests.post(_api("auth/register"), json={"user_id": sid, "password": "pw"}).status_code == 200
    token_seller = requests.post(_api("auth/login"), json={"user_id": sid, "password": "pw", "terminal": "t"}).json()["token"]
    assert requests.post(_api("auth/register"), json={"user_id": bid, "password": "pw"}).status_code == 200
    token_buyer = requests.post(_api("auth/login"), json={"user_id": bid, "password": "pw", "terminal": "t"}).json()["token"]

    # create store and add a book
    headers = {"token": token_seller}
    assert requests.post(_api("seller/create_store"), headers=headers, json={"user_id": sid, "store_id": st}).status_code == 200
    bi = {
        "id": book_id,
        "title": "SendAuth",
        "author": "A",
        "price": 1000,
        "isbn": "X-1",
        "pages": 123,
        "pub_year": 2024,
    }
    assert requests.post(_api("seller/add_book"), headers=headers, json={"user_id": sid, "store_id": st, "book_id": book_id, "stock_level": 2, "book_info": bi}).status_code == 200

    # create order and pay
    r = requests.post(_api("buyer/new_order"), json={"user_id": bid, "store_id": st, "books": [{"id": book_id, "count": 1}]})
    assert r.status_code == 200
    order_id = r.json()["order_id"]
    assert requests.post(_api("buyer/add_funds"), json={"user_id": bid, "password": "pw", "add_value": 1000}).status_code == 200
    r = requests.post(_api("buyer/payment"), json={"user_id": bid, "password": "pw", "order_id": order_id})
    assert r.status_code == 200

    # Insert a rogue latest status not in ('paid','shipped') after the paid one
    db = mongo_store.get_db()
    future_ts = int(time.time() * 1000) + 10000  # 毫秒级时间戳，确保比已存在的 'paid' 事件更新
    db["order_status"].insert_one({
        "order_id": order_id,
        "status": "created",
        "ts": future_ts,
        "user_id": bid,
        "store_id": st,
    })

    # Now send_books should return authorization fail (401) because latest status is not allowed
    resp = requests.post(_api("seller/send_books"), headers=headers, json={"user_id": sid, "order_id": order_id})
    assert resp.status_code == 401
