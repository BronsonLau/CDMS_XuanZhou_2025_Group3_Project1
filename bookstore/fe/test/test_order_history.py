import json
import time

from be.model.user_mongo import User
from be.model.seller_mongo import Seller
from be.model.buyer_mongo import Buyer


def test_order_history_flow():
    u = User()
    s = Seller()
    b = Buyer()

    buyer_id = "u_hist_buyer"
    seller_id = "u_hist_seller"
    store_id = "s_hist_1"
    book_id = "bk_hist_1"

    # register users
    assert u.register(buyer_id, "pw")[0] == 200
    assert u.register(seller_id, "pw")[0] == 200

    # create store
    assert s.create_store(seller_id, store_id)[0] == 200

    # add book with content/tags for search and text index fields
    book_info = {
        "id": book_id,
        "title": "FT Book",
        "author": "AU",
        "isbn": "9780000123",
        "price": 60,
        "pages": 200,
        "pub_year": 2024,
        "tags": ["历史", "检索"],
        "content": "这是一段用于全文索引匹配的内容",
        "book_intro": "简介段落",
    }
    assert s.add_book(seller_id, store_id, book_id, json.dumps(book_info), 10)[0] == 200

    # add funds and make an order
    assert b.add_funds(buyer_id, "pw", 1000)[0] == 200
    code, msg, order_id = b.new_order(buyer_id, store_id, [(book_id, 1)])
    assert code == 200 and order_id
    assert b.payment(buyer_id, "pw", order_id)[0] == 200

    # ship and receive
    assert s.send_books(seller_id, order_id)[0] == 200
    assert b.receive_books(buyer_id, order_id)[0] == 200

    # list orders
    code, msg, results = b.list_orders(buyer_id, page=1, size=10)
    assert code == 200
    assert any(r.get("order_id") == order_id and r.get("status") == "received" for r in results)
