import json
from be.model.search_mongo import Search, Filter
from be.model import mongo_store


def _insert_store_row(store_id, book_id, bi, stock):
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


def test_search_combined_ranges_and_isbn_mismatch():
    # two books with different numeric fields
    bi1 = {"title": "Alpha", "author": "A", "isbn": "I-001", "pub_year": 2022, "pages": 250, "price": 1500}
    bi2 = {"title": "Beta", "author": "B", "isbn": "I-002", "pub_year": 2018, "pages": 90, "price": 500}
    _insert_store_row("s_comb", "bk1", bi1, 5)
    _insert_store_row("s_comb", "bk2", bi2, 0)

    s = Search()
    f = Filter(store_id="s_comb")
    # set all ranges to include only bi1
    f.pages = [120, 300]
    f.price = [1000, 2000]
    f.publish_date = [2020, 2024]
    f.stock_level = [1, 10]

    code, msg, rows = s.search("a", f)  # keyword like on title
    assert code == 200 and any(r.get("isbn") == "I-001" for r in rows) and all(r.get("stock_level", 0) >= 1 for r in rows)

    # ISBN mismatch should filter out
    f.isbn = "NOT-THERE"
    code, msg, rows = s.search("a", f)
    assert code == 200 and len(rows) == 0
