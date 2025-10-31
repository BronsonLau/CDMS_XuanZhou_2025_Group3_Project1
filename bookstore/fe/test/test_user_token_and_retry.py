import uuid
from be.model.user_mongo import User
from be.model import mongo_store


def test_check_token_invalid_signature_branch():
    u = User()
    # 保证干净用户
    uid = f"u_ct_{str(uuid.uuid4())[:8]}"
    mongo_store.get_db()["user"].delete_one({"_id": uid})
    code, _ = u.register(uid, "p")
    assert code == 200
    # 从 Mongo 取 token
    row = mongo_store.get_db()["user"].find_one({"_id": uid}, {"token": 1})
    token = row.get("token", "") if row else ""
    # 用错误user_id 校验，命中 InvalidSignature 分支返回授权失败
    code, _ = u.check_token(uid + "x", token)
    assert code != 200


def test_register_retry_on_operational_error():
    u = User()
    uid = f"u_rr_{str(uuid.uuid4())[:8]}"

    # 模拟首次 Mongo insert_one 抛出 PyMongoError，触发 register 的重试逻辑
    fired = {"x": False}
    real_insert = u.col_users.insert_one

    def flaky_insert(doc):
        from pymongo.errors import PyMongoError
        if not fired["x"]:
            fired["x"] = True
            raise PyMongoError("transient")
        return real_insert(doc)

    u.col_users.insert_one = flaky_insert  # type: ignore[assignment]
    code, msg = u.register(uid, "p")
    assert code == 200
