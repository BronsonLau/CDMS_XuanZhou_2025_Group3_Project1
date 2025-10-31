import uuid
from be.model.seller_mongo import Seller
from be.model.user_mongo import User
from be.model import mongo_store


def test_create_store_retry_locked_succeeds():
    # Mongo-only：先注册用户，再创建店铺
    uid = "u_" + uuid.uuid4().hex[:6]
    sid = "st_" + uuid.uuid4().hex[:6]
    db = mongo_store.get_db()
    db["user"].delete_one({"_id": uid})
    User().register(uid, "p")
    s = Seller()
    code, msg = s.create_store(uid, sid)
    assert code == 200
