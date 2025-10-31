import uuid
from urllib.parse import urljoin
import requests
from fe import conf
from fe.access.book import BookDB
from fe.access.new_seller import register_new_seller


def _mk_store():
    sid = f"s_cov_{str(uuid.uuid4())[:8]}"
    pwd = "pass"
    s = register_new_seller(sid, pwd)
    store_id = f"st_cov_{str(uuid.uuid4())[:8]}"
    assert s.create_store(store_id) == 200
    books = BookDB(large=False).get_book_info(0, 6)
    for b in books:
        assert s.add_book(store_id, 5, b) == 200
    return s, store_id


def test_search_empty_keyword_and_store_filter():
    _, store_id = _mk_store()
    url = urljoin(conf.URL, "search/keyword")
    r = requests.post(url, json={"keyword": "", "filter": {"store_id": store_id}})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 6
    assert all(x.get("store_id") == store_id for x in data["results"]) or data["results"] == []


def test_search_equal_range_boundaries():
    _, store_id = _mk_store()
    url = urljoin(conf.URL, "search/keyword")
    pages = BookDB(large=False).get_book_info(0, 1)[0].pages
    payload = {"keyword": "Sample", "filter": {"store_id": store_id, "pages_from": pages, "pages_to": pages}}
    r = requests.post(url, json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 1


def test_pagination_last_page_empty():
    _, store_id = _mk_store()
    url = urljoin(conf.URL, "search/keyword")
    r1 = requests.post(url, json={"keyword": "Sample", "filter": {"store_id": store_id}, "page": 1, "size": 100})
    r2 = requests.post(url, json={"keyword": "Sample", "filter": {"store_id": store_id}, "page": 2, "size": 100})
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(r2.json().get("results", [])) == 0
