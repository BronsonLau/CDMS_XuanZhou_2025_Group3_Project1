from be.model.search_mongo import Search, Filter
from be.model import mongo_store


def test_search_minimal_document_returns():
    # 在 Mongo 版本中，没有 SQL 双重回退；这里验证最小字段的文档也能被返回
    inv = mongo_store.get_db()["inventory"]
    inv.delete_one({"store_id": "st_f", "book_id": "bk_f"})
    inv.insert_one({
        "store_id": "st_f",
        "book_id": "bk_f",
        "book_info": "{}",
        "stock_level": 7,
        "title": None,
        "author": None,
        "isbn": None,
        "pub_year": None,
        "pages": None,
        "price": None,
    })

    s = Search()
    code, msg, rows = s.search("", Filter(store_id="st_f"))
    assert code == 200 and len(rows) == 1
