from flask import Blueprint
from flask import request
from flask import jsonify
from be.model import user_mongo as user

bp_auth = Blueprint("auth", __name__, url_prefix="/auth")


@bp_auth.route("/login", methods=["POST"])
def login():
    user_id = request.json.get("user_id", "")
    password = request.json.get("password", "")
    terminal = request.json.get("terminal", "")
    u = user.User()
    try:
        code, message, token = u.login(
            user_id=user_id, password=password, terminal=terminal
        )
    finally:
        try:
            u.conn.close()  # 每次请求结束主动关闭连接，减少长时间持有导致的锁竞争
        except Exception:
            pass
    return jsonify({"message": message, "token": token}), code


@bp_auth.route("/logout", methods=["POST"])
def logout():
    user_id: str = request.json.get("user_id")
    token: str = request.headers.get("token")
    u = user.User()
    try:
        code, message = u.logout(user_id=user_id, token=token)
    finally:
        try:
            u.conn.close()  # 用后即弃，降低连接堆积
        except Exception:
            pass
    return jsonify({"message": message}), code


@bp_auth.route("/register", methods=["POST"])
def register():
    user_id = request.json.get("user_id", "")
    password = request.json.get("password", "")
    u = user.User()
    try:
        code, message = u.register(user_id=user_id, password=password)
    finally:
        try:
            u.conn.close()  # 注册并发多，及时关闭连接尤其重要
        except Exception:
            pass
    return jsonify({"message": message}), code


@bp_auth.route("/unregister", methods=["POST"])
def unregister():
    user_id = request.json.get("user_id", "")
    password = request.json.get("password", "")
    u = user.User()
    try:
        code, message = u.unregister(user_id=user_id, password=password)
    finally:
        try:
            u.conn.close()  # 与上同理，避免连接泄漏与锁占用
        except Exception:
            pass
    return jsonify({"message": message}), code


@bp_auth.route("/password", methods=["POST"])
def change_password():
    user_id = request.json.get("user_id", "")
    old_password = request.json.get("oldPassword", "")
    new_password = request.json.get("newPassword", "")
    u = user.User()
    try:
        code, message = u.change_password(
            user_id=user_id, old_password=old_password, new_password=new_password
        )
    finally:
        try:
            u.conn.close()  # 用后即弃
        except Exception:
            pass
    return jsonify({"message": message}), code
