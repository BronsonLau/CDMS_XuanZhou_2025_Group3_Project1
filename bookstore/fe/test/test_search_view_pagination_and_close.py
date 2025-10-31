import types
from urllib.parse import urljoin
import requests
from fe import conf


class _FakeConn:
    def close(self):
        raise RuntimeError("close boom")


class _FakeSearch:
    def __init__(self):
        self.conn = _FakeConn()

    def search(self, keyword, f):  # noqa: ANN001
        # 返回固定 3 条，便于分页切片验证
        rows = [
            {"store_id": "st", "book_id": f"bk{i}", "title": "T", "author": "A", "price": 1, "isbn": f"I{i}", "stock_level": 1}
            for i in range(3)
        ]
        return 200, "ok", rows


def test_search_view_page_and_size_normalization(monkeypatch):
    # 替换 Search 为假实现，以覆盖 finally 里 close 异常吞掉的分支，并测试 page/size 归一化
    import be.view.search as vsearch

    monkeypatch.setattr(vsearch, "Search", _FakeSearch)

    url = urljoin(conf.URL, "search/keyword")
    # 传入非法 page/size，应被归一化为 page=1, size=20，然后切片只返回前 3 条（全部）
    r = requests.post(url, json={"keyword": "", "filter": {}, "page": 0, "size": 0})
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 3
    assert len(data["results"]) == 3
