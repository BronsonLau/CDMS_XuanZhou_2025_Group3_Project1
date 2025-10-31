import json
from be.model.search import Search, Filter


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _ConnSingleFallback:
    def __init__(self):
        self._calls = 0

    def execute(self, sql, params=()):
        self._calls += 1
        if self._calls == 1:
            # initial SQL path raises no such column to trigger json_extract
            raise Exception("has no column named title")
        # json_extract path should be used, return a matching row
        bi = {"title": "Alpha Fallback", "author": "aa", "isbn": "F-1"}
        return _FakeCursor([(None, "bk", json.dumps(bi), 2)])


def test_search_single_fallback_json_extract():
    s = Search()
    s.conn = _ConnSingleFallback()  # type: ignore[assignment]
    f = Filter()
    code, msg, rows = s.search("alpha", f)
    assert code == 200 and any(r["isbn"] == "F-1" for r in rows)
