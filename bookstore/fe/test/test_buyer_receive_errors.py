import uuid
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access.book import BookDB


def test_receive_before_shipped_and_invalid_order():
    suffix = str(uuid.uuid4())[:8]
    seller_id = f"s_recv_{suffix}"
    buyer_id = f"b_recv_{suffix}"
    password = "pass"
    s = register_new_seller(seller_id, password)
    b = register_new_buyer(buyer_id, password)

    store_id = f"st_recv_{suffix}"
    assert s.create_store(store_id) == 200

    # 选一本书并上架
    db = BookDB(large=False)
    book = db.get_book_info(0, 1)[0]
    assert s.add_book(store_id, 5, book) == 200

    # 下单并支付
    code, order_id = b.new_order(store_id, [(book.id, 1)])
    assert code == 200
    assert b.add_funds(100000) == 200
    assert b.payment(order_id) == 200

    # 未发货前收货应失败
    assert b.receive_books(order_id) != 200

    # 无效订单ID收货也应失败
    assert b.receive_books("no_such_order") != 200
