import uuid
from fe.access.auth import Auth
from fe import conf


def test_double_logout_and_wrong_change_password():
    uid = f"u_ue_{str(uuid.uuid4())[:8]}"
    pwd = "pass"
    a = Auth(conf.URL)
    assert a.register(uid, pwd) == 200
    code, token = a.login(uid, pwd, "t")
    assert code == 200 and token
    # 正常登出
    assert a.logout(uid, token) == 200
    # 再次登出（无效会话）应失败
    assert a.logout(uid, token) != 200
    # 错误旧密码修改
    assert a.password(uid, old_password="wrong", new_password="new") != 200
