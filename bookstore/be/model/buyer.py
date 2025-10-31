"""SQLite 版本已移除。请使用 Mongo 版本 Buyer。

该模块保留仅为兼容历史导入，所有逻辑委托给 buyer_mongo.Buyer。
"""

from .buyer_mongo import Buyer  # noqa: F401
