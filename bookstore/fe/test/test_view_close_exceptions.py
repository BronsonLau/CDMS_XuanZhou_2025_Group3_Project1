import requests
from urllib.parse import urljoin
from fe import conf


def _url(p: str) -> str:
    return urljoin(conf.URL, p)


def test_auth_views_conn_close_exception(monkeypatch):
    class FakeConn:
        def close(self):
            raise RuntimeError("close boom")

    class FakeUser:
        def __init__(self):
            self.conn = FakeConn()

        def login(self, user_id, password, terminal):
            return 200, "ok", "tok"

        def logout(self, user_id, token):
            return 200, "ok"

        def register(self, user_id, password):
            return 200, "ok"

        def unregister(self, user_id, password):
            return 200, "ok"

        def change_password(self, user_id, old_password, new_password):
            return 200, "ok"

    # Patch the User class used by the blueprint
    monkeypatch.setattr("be.view.auth.user.User", FakeUser, raising=True)

    # Each endpoint should still return 200 and ignore close errors
    r = requests.post(_url("auth/login"), json={"user_id": "u", "password": "p", "terminal": "t"})
    assert r.status_code == 200 and r.json().get("token") == "tok"

    r = requests.post(_url("auth/register"), json={"user_id": "u2", "password": "p"})
    assert r.status_code == 200

    r = requests.post(_url("auth/password"), json={"user_id": "u", "oldPassword": "p", "newPassword": "p2"})
    assert r.status_code == 200

    r = requests.post(_url("auth/unregister"), json={"user_id": "u", "password": "p"})
    assert r.status_code == 200

    r = requests.post(_url("auth/logout"), headers={"token": "tok"}, json={"user_id": "u"})
    assert r.status_code == 200


def test_buyer_views_conn_close_exception(monkeypatch):
    class FakeConn:
        def close(self):
            raise RuntimeError("close boom")

    class FakeBuyer:
        def __init__(self):
            self.conn = FakeConn()

        def new_order(self, user_id, store_id, id_and_count):
            return 200, "ok", "oid"

        def payment(self, user_id, password, order_id):
            return 200, "ok"

        def add_funds(self, user_id, password, add_value):
            return 200, "ok"

        def receive_books(self, user_id, order_id):
            return 200, "ok"

        def cancel_order(self, user_id, order_id):
            return 200, "ok"

    monkeypatch.setattr("be.view.buyer.Buyer", FakeBuyer, raising=True)

    r = requests.post(_url("buyer/new_order"), json={"user_id": "u", "store_id": "s", "books": []})
    assert r.status_code == 200 and r.json().get("order_id") == "oid"

    r = requests.post(_url("buyer/payment"), json={"user_id": "u", "order_id": "oid", "password": "p"})
    assert r.status_code == 200

    r = requests.post(_url("buyer/add_funds"), json={"user_id": "u", "password": "p", "add_value": 1})
    assert r.status_code == 200

    r = requests.post(_url("buyer/receive_book"), json={"user_id": "u", "order_id": "oid"})
    assert r.status_code == 200

    r = requests.post(_url("buyer/cancel_order"), json={"user_id": "u", "order_id": "oid"})
    assert r.status_code == 200
