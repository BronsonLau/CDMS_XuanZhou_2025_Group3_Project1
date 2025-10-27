from flask import Blueprint
from flask import request
from flask import jsonify
from be.model import buyer_mongo as buyer

# Expose Buyer symbol for tests that monkeypatch be.view.buyer.Buyer
Buyer = buyer.Buyer

bp_buyer = Blueprint("buyer", __name__, url_prefix="/buyer")


@bp_buyer.route("/new_order", methods=["POST"])
def new_order():
    user_id: str = request.json.get("user_id")
    store_id: str = request.json.get("store_id")
    books = request.json.get("books") or []  # 容错：若缺失 books 字段则视为 []，避免类型报错
    id_and_count = []
    for book in books:
        book_id = book.get("id")
        count = book.get("count")
        id_and_count.append((book_id, count))

    b = Buyer()
    try:
        code, message, order_id = b.new_order(user_id, store_id, id_and_count)
    finally:
        try:
            b.conn.close()  # 请求结束主动关闭连接，减少长时间持有导致的锁竞争
        except Exception:
            pass
    return jsonify({"message": message, "order_id": order_id}), code


@bp_buyer.route("/payment", methods=["POST"])
def payment():
    user_id: str = request.json.get("user_id")
    order_id: str = request.json.get("order_id")
    password: str = request.json.get("password")
    b = Buyer()
    try:
        code, message = b.payment(user_id, password, order_id)
    finally:
        try:
            b.conn.close()  # 用后即弃
        except Exception:
            pass
    return jsonify({"message": message}), code


@bp_buyer.route("/add_funds", methods=["POST"])
def add_funds():
    user_id = request.json.get("user_id")
    password = request.json.get("password")
    add_value = request.json.get("add_value")
    b = Buyer()
    try:
        code, message = b.add_funds(user_id, password, add_value)
    finally:
        try:
            b.conn.close()  # 用后即弃
        except Exception:
            pass
    return jsonify({"message": message}), code

# receive_book
@bp_buyer.route("/receive_book", methods=["POST"])
def receive_books():
    user_id = request.json.get("user_id")
    order_id = request.json.get("order_id")
    b = Buyer()
    try:
        code, message = b.receive_books(user_id, order_id)
    finally:
        try:
            b.conn.close()  # 用后即弃
        except Exception:
            pass
    return jsonify({"message": message}), code

# cancel_order
@bp_buyer.route("/cancel_order", methods=["POST"])
def cancel_order():
    user_id = request.json.get("user_id")
    order_id = request.json.get("order_id")
    b = Buyer()
    try:
        code, message = b.cancel_order(user_id, order_id)
    finally:
        try:
            b.conn.close()  # 用后即弃
        except Exception:
            pass
    return jsonify({"message": message}), code

# list orders (history)
@bp_buyer.route("/orders", methods=["POST"])
def list_orders():
    user_id = request.json.get("user_id")
    page = request.json.get("page", 1)
    size = request.json.get("size", 20)
    status = request.json.get("status")  # optional filter
    b = Buyer()
    try:
        code, message, results = b.list_orders(user_id=user_id, page=page, size=size, status=status)
    finally:
        try:
            b.conn.close()
        except Exception:
            pass
    return jsonify({"message": message, "count": len(results), "results": results}), code