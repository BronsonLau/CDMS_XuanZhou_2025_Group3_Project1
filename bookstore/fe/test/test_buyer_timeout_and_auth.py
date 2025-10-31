import json
import time

from be.model.user_mongo import User
from be.model.seller_mongo import Seller
from be.model.buyer_mongo import Buyer
from be.model import mongo_store


def _setup_basic_store():
    u = User()
    s = Seller()
    b = Buyer()
    buyer_id = "u_to_buyer"
    seller_id = "u_to_seller"
    store_id = "st_to_1"
    book_id = "bk_to_1"

    # register users and create store
    u.register(buyer_id, "pw")
    u.register(seller_id, "pw")
    s.create_store(seller_id, store_id)

    # add one book
    book_info = {
        "id": book_id,
        "title": "TO Book",
        "author": "AU",
        "isbn": "9780000456",
        "price": 50,
        "pages": 150,
        "pub_year": 2024,
        "tags": ["超时", "授权"],
        "content": "用于覆盖 _lazy_timeout_check_mongo 和授权失败分支",
    }
    s.add_book(seller_id, store_id, book_id, json.dumps(book_info), 5)
    return u, s, b, buyer_id, seller_id, store_id, book_id


def test_payment_times_out_marks_order_timed_out():
    u, s, b, buyer_id, seller_id, store_id, book_id = _setup_basic_store()

    # add funds and create order
    assert b.add_funds(buyer_id, "pw", 1000)[0] == 200
    code, msg, order_id = b.new_order(buyer_id, store_id, [(book_id, 1)])
    assert code == 200 and order_id

    # make order timed out by moving created_ts to the far past (milliseconds)
    db = mongo_store.get_db()
    past_ms = int((time.time() - (Buyer.ORDER_TIMEOUT_SECONDS + 5)) * 1000)
    db["orders"].update_one({"_id": order_id}, {"$set": {"created_ts": past_ms}})

    # payment should detect timeout and refuse
    code, msg = b.payment(buyer_id, "pw", order_id)
    assert code == 529

    # ensure a timed_out status is recorded
    latest = list(db["order_status"].find({"order_id": order_id}).sort([("ts", -1)]).limit(1))
    assert latest and latest[0].get("status") in ("timed_out", "canceled")


def test_receive_books_authorization_fail_for_other_user():
    u, s, b, buyer_id, seller_id, store_id, book_id = _setup_basic_store()

    # another buyer
    other_buyer = "u_other"
    u.register(other_buyer, "pw")

    # funds, order, pay, ship
    assert b.add_funds(buyer_id, "pw", 1000)[0] == 200
    code, msg, order_id = b.new_order(buyer_id, store_id, [(book_id, 1)])
    assert code == 200 and order_id
    assert b.payment(buyer_id, "pw", order_id)[0] == 200
    assert s.send_books(seller_id, order_id)[0] == 200

    # other user tries to receive -> authorization fail
    code, msg = b.receive_books(other_buyer, order_id)
    assert code == 401
