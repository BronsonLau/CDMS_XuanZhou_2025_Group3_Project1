import time
from be.model.user_mongo import User, jwt_encode, jwt_decode
from be.model import mongo_store


def test_jwt_encode_decode_and_invalid():
    token = jwt_encode("u_jwt", "t1")
    payload = jwt_decode(token, "u_jwt")
    assert payload["user_id"] == "u_jwt"
    # 无效签名
    try:
        jwt_decode(token, "wrong_user")
        assert False, "should raise"
    except Exception:
        pass


def test_user_register_duplicate_via_model():
    u = User()
    db = mongo_store.get_db()
    # 保证干净环境（Mongo）
    db["user"].delete_one({"_id": "u_dup"})
    code, _ = u.register("u_dup", "p")
    assert code == 200
    code, _ = u.register("u_dup", "p")
    assert code == 512
