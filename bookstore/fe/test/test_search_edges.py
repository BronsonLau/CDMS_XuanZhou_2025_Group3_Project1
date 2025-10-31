import uuid
from fe import conf
import requests
from urllib.parse import urljoin
from be.model.search_mongo import Search, Filter
from be.model import mongo_store


def test_search_filter_non_numeric_and_stock_upper_bound():
    # 构造一条包含非数字 pages/price/pub_year 的书目，验证过滤器对范围的排除
    store_id = f"st_se_{str(uuid.uuid4())[:8]}"
    # 插入 inventory 记录，pages/price/pub_year 非数字以字符串形式存在于 book_info，冗余字段留空
    inv = mongo_store.get_db()["inventory"]
    inv.delete_one({"store_id": store_id, "book_id": "bad_1"})
    bi = {"title": "X", "author": "Y", "isbn": "NNN", "pages": "notint", "price": "n/a", "pub_year": "bad"}
    inv.insert_one({
        "store_id": store_id,
        "book_id": "bad_1",
        "book_info": __import__("json").dumps(bi),
        "stock_level": 10,
        "title": None,
        "author": None,
        "isbn": None,
        "pub_year": None,
        "pages": None,
        "price": None,
    })

    s = Search()
    f = Filter(isbn=None, pages=[100, 200], price=[100, 2000], publish_date=[1999, 2025], stock_level=[None, 5], store_id=store_id)
    code, msg, res = s.search("", f)
    # stock 上界为 5，但该条为 10，应被排除；同时非数字 pages/price/year 在范围过滤下也会被排除
    assert code == 200 and len(res) == 0


def test_search_view_pagination_bounds():
    # 插入几条正常数据
    sid = f"st_pg_{str(uuid.uuid4())[:8]}"
    inv = mongo_store.get_db()["inventory"]
    for i in range(3):
        bi = {"title": f"T{i}", "author": "A", "isbn": f"I{i}", "pages": 150, "price": 1000, "pub_year": 2024}
        inv.delete_one({"store_id": sid, "book_id": f"b{i}"})
        inv.insert_one({
            "store_id": sid,
            "book_id": f"b{i}",
            "book_info": __import__("json").dumps(bi),
            "stock_level": 1,
            "title": bi["title"],
            "author": bi["author"],
            "isbn": bi["isbn"],
            "pub_year": bi["pub_year"],
            "pages": bi["pages"],
            "price": bi["price"],
        })

    url = urljoin(conf.URL, "search/keyword")
    # 传递非法 page/size，视图应归一到 page=1,size=20，不报错
    r = requests.post(url, json={"keyword": "T", "filter": {"store_id": sid}, "page": 0, "size": 0})
    assert r.status_code == 200
    data = r.json()
    # 返回的 paged 会包含所有3条（size 归一为20）
    assert data["count"] >= 3 and len(data["results"]) >= 3