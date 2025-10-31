import json
from be.model.search_mongo import Search, Filter
from be.model import mongo_store


def _insert_raw_store(store_id: str, book_id: str, book_info: str, stock: int):
    # 直接写入一条 Mongo inventory 记录，覆盖 Search 的回退/容错路径
    inv = mongo_store.get_db()["inventory"]
    inv.delete_one({"store_id": store_id, "book_id": book_id})
    inv.insert_one(
        {
            "store_id": store_id,
            "book_id": book_id,
            "book_info": book_info,
            "stock_level": int(stock),
            "title": None,
            "author": None,
            "isbn": None,
            "pub_year": None,
            "pages": None,
            "price": None,
        }
    )


def test_search_malformed_bookinfo_and_filters():
    # 插入一条 book_info 非 JSON 的记录，验证 Search 的异常容错与过滤（Mongo）
    _insert_raw_store("s_search_ut", "bk_x", "{not-json}", 5)

    s = Search()
    f = Filter()
    f.store_id = "s_search_ut"
    # 关键词为空，命中容错路径；再加上 stock 下限，仍应返回记录
    code, msg, rows = s.search("", f)
    assert code == 200 and len(rows) >= 1

    f.stock_level = [10, None]  # 提高下限以过滤掉该条
    code, msg, rows = s.search("", f)
    assert code == 200 and all(r.get("stock_level", 0) >= 10 for r in rows)


def test_search_isbn_exact_and_keyword_like():
    # 插入一条完整 JSON 的记录，覆盖 isbn 精确匹配与关键字匹配（Mongo）
    bi = {
        "id": "bk_y",
        "title": "UT Alpha",
        "author": "ZZZ",
        "isbn": "UT-ISBN-001",
        "pages": 222,
        "price": 1999,
        "pub_year": 2023,
    }
    payload = json.dumps(bi)
    inv = mongo_store.get_db()["inventory"]
    inv.delete_one({"store_id": "s_search_ut2", "book_id": "bk_y"})
    inv.insert_one(
        {
            "store_id": "s_search_ut2",
            "book_id": "bk_y",
            "book_info": payload,
            "stock_level": 3,
            "title": bi["title"],
            "author": bi["author"],
            "isbn": bi["isbn"],
            "pub_year": bi["pub_year"],
            "pages": bi["pages"],
            "price": bi["price"],
        }
    )

    s = Search()
    f = Filter(store_id="s_search_ut2", isbn="UT-ISBN-001")
    code, msg, rows = s.search("alpha", f)
    assert code == 200 and any(r.get("isbn") == "UT-ISBN-001" for r in rows)
