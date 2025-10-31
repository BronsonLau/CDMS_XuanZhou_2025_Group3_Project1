import json
from be.model.search_mongo import Search, Filter
from be.model import mongo_store


def _insert(store_id: str, book_id: str, bi: dict, stock: int):
    payload = json.dumps(bi)
    inv = mongo_store.get_db()["inventory"]
    inv.delete_one({"store_id": store_id, "book_id": book_id})
    inv.insert_one(
        {
            "store_id": store_id,
            "book_id": book_id,
            "book_info": payload,
            "stock_level": int(stock),
            "title": bi.get("title"),
            "author": bi.get("author"),
            "isbn": bi.get("isbn"),
            "pub_year": bi.get("pub_year"),
            "pages": bi.get("pages"),
            "price": bi.get("price"),
        }
    )


def test_filter_with_non_numeric_pages_price_year():
    bi = {
        "id": "bk_nonnum",
        "title": "NumEdge",
        "author": "A",
        "isbn": "N-1",
        "pages": "abc",  # 非数字
        "price": "xyz",  # 非数字
        "pub_year": "unknown",  # 非数字
    }
    _insert("s_numtol", "bk_nonnum", bi, 5)

    s = Search()
    f = Filter(store_id="s_numtol")
    # 设置下限，按照实现，如果字段不可转为 int，会被视为 None，且有下限时应过滤掉
    f.pages = [1, None]
    f.price = [1, None]
    f.publish_date = [2000, None]
    code, msg, rows = s.search("NumEdge", f)
    assert code == 200 and all(r.get("stock_level", 0) >= 0 for r in rows) and len(rows) == 0

    # 取消这些范围限制后，应可返回
    f.pages = [None, None]
    f.price = [None, None]
    f.publish_date = [None, None]
    code, msg, rows = s.search("NumEdge", f)
    assert code == 200 and any(r.get("book_id") == "bk_nonnum" for r in rows)
