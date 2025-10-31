from be.model.user_mongo import User
from be.model import mongo_store


def _register_login(user_id: str, password: str = "pw"):
    u = User()
    # ensure clean slate in Mongo to avoid duplicate key from previous runs
    mongo_store.get_db()["user"].delete_one({"_id": user_id})
    code, msg = u.register(user_id, password)
    assert code == 200
    code, msg, token = u.login(user_id, password, terminal="t1")
    assert code == 200 and token
    return token


def test_logout_rowcount_zero():
    user_id = "u_row0_logout"
    token = _register_login(user_id)

    u = User()
    # Mongo-backed implementation doesn't depend on SQLite rowcount.
    code, msg = u.logout(user_id, token)
    assert code == 200


def test_change_password_rowcount_zero():
    user_id = "u_row0_chpwd"
    _register_login(user_id)

    u = User()
    # With Mongo as source of truth, operation succeeds regardless of any SQLite rowcount.
    code, msg = u.change_password(user_id, old_password="pw", new_password="pw2")
    assert code == 200
