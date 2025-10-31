from be.model import mongo_store
from be.model.search_mongo import Search, Filter


def test_mongo_ensure_indexes_tolerated():
    # 确认在 Mongo-only 模式下，ensure_indexes(None) 不会抛异常
    mongo_store.ensure_indexes(None)


def test_search_outer_exception_returns_528(monkeypatch):
    s = Search()

    # 通过 monkeypatch 切断底层 find 调用以触发外层异常路径
    def boom_find(*a, **k):
        raise ValueError("boom-outer")

    monkeypatch.setattr(s.col_inventory, "find", boom_find)
    code, msg, rows = s.search("k", Filter())
    assert code == 528 and rows == []
