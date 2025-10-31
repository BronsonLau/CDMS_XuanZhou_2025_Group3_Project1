import json
import requests
from fe import conf


def test_search_view_negative_pagination():
    url = conf.URL + "search/keyword"
    # body with negative page/size should be corrected to defaults
    body = {
        "keyword": "",
        "page": -1,
        "size": -5,
        "filter": {"store_id": None},
    }
    r = requests.post(url, json=body, timeout=5)
    assert r.status_code == 200
    data = r.json()
    # should contain message and results list
    assert "message" in data and isinstance(data.get("results"), list)
