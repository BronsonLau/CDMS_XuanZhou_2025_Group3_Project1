import uuid
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.access.book import BookDB
from fe import conf
import requests
from urllib.parse import urljoin


def test_search_keyword_and_pagination():
    # prepare store with a few books
    suffix = str(uuid.uuid4())[:8]
    seller_id = f"s_search_{suffix}"
    buyer_id = f"b_search_{suffix}"
    password = "pass"
    s = register_new_seller(seller_id, password)
    _ = register_new_buyer(buyer_id, password)

    store_id = f"st_search_{suffix}"
    assert s.create_store(store_id) == 200

    db = BookDB(large=False)
    books = db.get_book_info(0, 5)
    for b in books:
        assert s.add_book(store_id, 3, b) == 200

    # search by a word present in title pattern "Sample Book"
    url = urljoin(conf.URL, "search/keyword")
    r = requests.post(url, json={"keyword": "Sample", "filter": {"store_id": store_id}, "page": 1, "size": 2})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] >= 5  # total in store
    assert len(data["results"]) == 2

    # second page
    r2 = requests.post(url, json={"keyword": "Sample", "filter": {"store_id": store_id}, "page": 2, "size": 2})
    assert r2.status_code == 200
    data2 = r2.json()
    assert len(data2["results"]) == 2
