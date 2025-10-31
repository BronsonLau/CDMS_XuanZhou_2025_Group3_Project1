import json

from be.model.seller_mongo import Seller
from be.model.search_mongo import Search, Filter
from be.model.user_mongo import User


def test_search_fulltext_on_content_and_tags():
    u = User()
    s = Seller()
    buyer_id = "u_ft_b"
    seller_id = "u_ft_s"
    store_id = "s_ft_1"
    book_id = "bk_ft_1"

    # users and store
    assert u.register(buyer_id, "pw")[0] in (200, 511)
    assert u.register(seller_id, "pw")[0] in (200, 511)
    assert s.create_store(seller_id, store_id)[0] in (200, 511)

    # add a book with content-only keyword
    kw = "全文索引特有关键字"
    book_info = {
        "id": book_id,
        "title": "Normal Title",
        "author": "A",
        "isbn": "9780000456",
        "price": 50,
        "pages": 120,
        "pub_year": 2023,
        "tags": ["测试标签", "另一个标签"],
        "content": f"这里包含 {kw} 来验证全文匹配",
    }
    assert s.add_book(seller_id, store_id, book_id, json.dumps(book_info), 5)[0] in (200, 518)

    # search by keyword (should match content/tags via text index or fallback)
    searcher = Search()
    f = Filter()
    code, msg, results = searcher.search(kw, f)
    assert code == 200
    assert any(r.get("book_id") == book_id for r in results)
