"""
该模块保留仅为兼容历史导入，所有逻辑委托给 buyer_mongo.Buyer。
"""

from .buyer_mongo import Buyer  # noqa: F401
