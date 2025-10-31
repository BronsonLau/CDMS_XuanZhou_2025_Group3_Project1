import requests
from urllib.parse import urljoin
from fe import conf


def _url(p: str) -> str:
    return urljoin(conf.URL, p)


def test_send_books_after_received_idempotent():
    sid = "seller_after"
    bid = "buyer_after"
    st = "store_after"
    bk = "bk_after"

    # register/login
    assert requests.post(_url("auth/register"), json={"user_id": sid, "password": "pw"}).status_code == 200
    token_seller = requests.post(_url("auth/login"), json={"user_id": sid, "password": "pw", "terminal": "t"}).json()["token"]
    assert requests.post(_url("auth/register"), json={"user_id": bid, "password": "pw"}).status_code == 200
    token_buyer = requests.post(_url("auth/login"), json={"user_id": bid, "password": "pw", "terminal": "t"}).json()["token"]

    headers = {"token": token_seller}
    assert requests.post(_url("seller/create_store"), headers=headers, json={"user_id": sid, "store_id": st}).status_code == 200
    bi = {"id": bk, "title": "TT", "author": "AA", "isbn": "IS1", "price": 1000}
    assert requests.post(_url("seller/add_book"), headers=headers, json={"user_id": sid, "store_id": st, "book_id": bk, "stock_level": 1, "book_info": bi}).status_code == 200

    r = requests.post(_url("buyer/new_order"), json={"user_id": bid, "store_id": st, "books": [{"id": bk, "count": 1}]})
    assert r.status_code == 200
    order_id = r.json()["order_id"]
    assert requests.post(_url("buyer/add_funds"), json={"user_id": bid, "password": "pw", "add_value": 1000}).status_code == 200
    assert requests.post(_url("buyer/payment"), json={"user_id": bid, "password": "pw", "order_id": order_id}).status_code == 200

    # seller ships
    assert requests.post(_url("seller/send_books"), headers=headers, json={"user_id": sid, "order_id": order_id}).status_code == 200
    # buyer receives
    assert requests.post(_url("buyer/receive_book"), json={"user_id": bid, "order_id": order_id}).status_code == 200
    # seller send again: should be idempotent 200
    assert requests.post(_url("seller/send_books"), headers=headers, json={"user_id": sid, "order_id": order_id}).status_code == 200
