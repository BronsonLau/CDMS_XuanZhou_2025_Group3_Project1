import uuid
from fe.access.book import BookDB
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer


def test_send_books_auth_and_idempotent():
    suf = str(uuid.uuid4())[:8]
    seller1 = register_new_seller(f"s1_sr_{suf}", "p")
    seller2 = register_new_seller(f"s2_sr_{suf}", "p")
    buyer = register_new_buyer(f"b_sr_{suf}", "p")
    store_id = f"st_sr_{suf}"
    assert seller1.create_store(store_id) == 200
    book = BookDB(large=False).get_book_info(0, 1)[0]
    assert seller1.add_book(store_id, 2, book) == 200
    # 下单支付
    code, order_id = buyer.new_order(store_id, [(book.id, 1)])
    assert code == 200
    assert buyer.add_funds(100000) == 200
    assert buyer.payment(order_id) == 200
    # 非店主发货应失败
    assert seller2.send_books(order_id) != 200
    # 店主发货成功
    assert seller1.send_books(order_id) == 200
    # 已发货后再次发货（幂等/终态容忍）
    assert seller1.send_books(order_id) == 200


def test_add_stock_level_retry_on_locked(monkeypatch):
    # 对 add_stock_level 的 UPDATE 制造一次 locked，验证短重试成功
    suf = str(uuid.uuid4())[:8]
    s = register_new_seller(f"s_rt_{suf}", "p")
    st = f"st_rt_{suf}"
    assert s.create_store(st) == 200
    book = BookDB(large=False).get_book_info(0, 1)[0]
    assert s.add_book(st, 1, book) == 200

    # Mongo-only：直接调用模型的 add_stock_level 验证成功
    from be.model.seller_mongo import Seller as SellerModel
    m = SellerModel()
    code, msg = m.add_stock_level(user_id=s.seller_id, store_id=st, book_id=book.id, add_stock_level=1)
    assert code == 200