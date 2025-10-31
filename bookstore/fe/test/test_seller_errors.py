import uuid
from fe.access.book import BookDB
from fe.access.new_seller import register_new_seller


def test_add_book_to_non_exist_store():
    s = register_new_seller(f"s_se_{str(uuid.uuid4())[:8]}", "pass")
    book = BookDB(large=False).get_book_info(0, 1)[0]
    code = s.add_book(store_id="not_exist_store", stock_level=5, book_info=book)
    assert code != 200


def test_add_book_duplicate_book_id():
    s = register_new_seller(f"s_se_{str(uuid.uuid4())[:8]}", "pass")
    store_id = f"st_se_{str(uuid.uuid4())[:8]}"
    assert s.create_store(store_id) == 200
    book = BookDB(large=False).get_book_info(0, 1)[0]
    assert s.add_book(store_id, 5, book) == 200
    # 再次添加同一本，预期失败
    assert s.add_book(store_id, 5, book) != 200


def test_add_stock_level_non_exist_book():
    s = register_new_seller(f"s_se_{str(uuid.uuid4())[:8]}", "pass")
    store_id = f"st_se_{str(uuid.uuid4())[:8]}"
    assert s.create_store(store_id) == 200
    # 对不存在的书加库存
    code = s.add_stock_level(seller_id=s.seller_id, store_id=store_id, book_id="bk_not_exist", add_stock_num=1)
    assert code != 200
