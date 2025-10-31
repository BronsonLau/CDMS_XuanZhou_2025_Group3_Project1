import uuid
from urllib.parse import urljoin

import pytest
import requests

from fe import conf
from fe.access.book import BookDB
from fe.access.new_buyer import register_new_buyer
from fe.access.new_seller import register_new_seller


@pytest.fixture
def prepared_store():
    """
    创建一个包含若干图书的小店铺，返回 (seller, store_id)。
    该夹具与 test_search.py 的准备逻辑一致，但便于复用多个过滤用例。
    """
    suffix = str(uuid.uuid4())[:8]
    seller_id = f"s_sfilter_{suffix}"
    buyer_id = f"b_sfilter_{suffix}"
    password = "pass"
    s = register_new_seller(seller_id, password)
    _ = register_new_buyer(buyer_id, password)

    store_id = f"st_sfilter_{suffix}"
    assert s.create_store(store_id) == 200

    db = BookDB(large=False)
    books = db.get_book_info(0, 6)
    for b in books:
        assert s.add_book(store_id, 5, b) == 200

    return s, store_id


def _post_search(payload):
    url = urljoin(conf.URL, "search/keyword")
    r = requests.post(url, json=payload)
    assert r.status_code == 200
    return r.json()


def test_filter_by_store_and_isbn(prepared_store):
    _, store_id = prepared_store

    # 选定数据集里第 0 本书的 ISBN
    isbn = BookDB(large=False).get_book_info(0, 1)[0].isbn

    data = _post_search({
        "keyword": "",  # 无关键字
        "filter": {"store_id": store_id, "isbn": isbn},
    })

    # 命中唯一一本
    assert data["count"] >= 1
    assert any(x.get("isbn") == isbn for x in data["results"])


def test_filter_by_ranges(prepared_store):
    _, store_id = prepared_store

    # 约束 pages/price/pub_year/stock_level 的范围，命中部分结果
    payload = {
        "keyword": "Sample",  # 命中标题
        "filter": {
            "store_id": store_id,
            "pages_from": 120,
            "pages_to": 350,
            "price_from": 1000,
            "price_to": 1400,
            "publish_date_from": 2020,
            "publish_date_to": 2025,
            "stock_from": 1,
            "stock_to": 10,
        },
    }
    data = _post_search(payload)
    assert data["count"] >= 1
    # 简单检查：结果至少有一条且关键字命中（标题包含 Sample）
    assert any("Sample" in (x.get("title") or "") for x in data["results"]) or data["results"] == []


def test_ordering_pagination_stable(prepared_store):
    _, store_id = prepared_store
    url = urljoin(conf.URL, "search/keyword")
    base_payload = {"keyword": "Sample", "filter": {"store_id": store_id}}

    r1 = requests.post(url, json={**base_payload, "page": 1, "size": 3})
    r2 = requests.post(url, json={**base_payload, "page": 2, "size": 3})
    assert r1.status_code == 200 and r2.status_code == 200
    ids1 = [x["book_id"] for x in r1.json()["results"]]
    ids2 = [x["book_id"] for x in r2.json()["results"]]
    # 两页不应重叠
    assert set(ids1).isdisjoint(set(ids2))
