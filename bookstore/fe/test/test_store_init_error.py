from be.model import mongo_store, store_mongo


def test_mongo_index_setup_noop_on_none():
    """Mongo-only: 确认索引初始化在传入 None 时为 no-op，不会抛异常。

    旧测试覆盖 SQLite 初始化的异常路径；Mongo 语义下，不再依赖 SQLite，
    这里改为验证我们的索引初始化函数在缺省/空 DB 时安全返回。
    """
    mongo_store.ensure_indexes(None)
    store_mongo.ensure_indexes(None)