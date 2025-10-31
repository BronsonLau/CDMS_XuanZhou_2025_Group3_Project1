import uuid
from fe import conf
import requests
from urllib.parse import urljoin
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access.book import BookDB


def test_new_order_missing_books_field_defaults():
    # 直接调接口，缺少 books 字段应被视为 [] 并不报错，但也会因缺少具体书籍而创建空订单失败
    # 这里我们传入空数组，以覆盖 buyer 视图对 books 缺省处理的分支
    suffix = str(uuid.uuid4())[:8]
    buyer_id = f"b_nb_{suffix}"
    password = "pass"
    register_new_buyer(buyer_id, password)
    url = urljoin(conf.URL, "buyer/new_order")
    r = requests.post(url, json={"user_id": buyer_id, "store_id": f"st_nb_{suffix}"})
    assert r.status_code != 200


def test_payment_missing_store_mapping():
    # 构造一个用户与订单，但删除 user_store 记录以触发 payment 中的卖家查找失败分支
    suffix = str(uuid.uuid4())[:8]
    seller_id = f"s_ms_{suffix}"
    buyer_id = f"b_ms_{suffix}"
    password = "pass"
    s = register_new_seller(seller_id, password)
    b = register_new_buyer(buyer_id, password)
    store_id = f"st_ms_{suffix}"
    assert s.create_store(store_id) == 200
    db = BookDB(large=False)
    book = db.get_book_info(0, 1)[0]
    assert s.add_book(store_id, 1, book) == 200
    code, order_id = b.new_order(store_id, [(book.id, 1)])
    assert code == 200
    # 删除 Mongo 中的 stores 文档，使得在 payment 中无法找到卖家
    from be.model import mongo_store
    db = mongo_store.get_db()
    db["stores"].delete_one({"_id": store_id})

    # 充值足够金额
    assert b.add_funds(100000) == 200
    # 支付时应返回店铺不存在错误
    assert b.payment(order_id) != 200


def test_bookdb_small_path_and_get_book_count():
    db = BookDB(large=False)
    cnt = db.get_book_count()
    assert cnt >= 0
    books = db.get_book_info(0, 3)
    assert len(books) == 3
    assert books[0].id.startswith("bk_")
