from flask import Blueprint
from flask import request
from flask import jsonify
from be.model import seller_mongo as seller
import json

bp_seller = Blueprint("seller", __name__, url_prefix="/seller")


@bp_seller.route("/create_store", methods=["POST"])
def seller_create_store():
    user_id: str = request.json.get("user_id")
    store_id: str = request.json.get("store_id")
    s = seller.Seller()
    try:
        code, message = s.create_store(user_id, store_id)
    finally:
        try:
            s.conn.close()  # 每次请求结束关闭连接，避免持有写锁
        except Exception:
            pass
    return jsonify({"message": message}), code


@bp_seller.route("/add_book", methods=["POST"])
def seller_add_book():
    user_id: str = request.json.get("user_id")
    store_id: str = request.json.get("store_id")
    book_info: str = request.json.get("book_info")
    stock_level: str = request.json.get("stock_level", 0)

    s = seller.Seller()
    try:
        code, message = s.add_book(
            user_id, store_id, book_info.get("id"), json.dumps(book_info), stock_level
        )
    finally:
        try:
            s.conn.close()  # 用后即弃，降低锁竞争
        except Exception:
            pass

    return jsonify({"message": message}), code


@bp_seller.route("/add_stock_level", methods=["POST"])
def add_stock_level():
    user_id: str = request.json.get("user_id")
    store_id: str = request.json.get("store_id")
    book_id: str = request.json.get("book_id")
    add_num: str = request.json.get("add_stock_level", 0)

    s = seller.Seller()
    try:
        code, message = s.add_stock_level(user_id, store_id, book_id, add_num)
    finally:
        try:
            s.conn.close()  # 用后即弃
        except Exception:
            pass

    return jsonify({"message": message}), code

#send_books
@bp_seller.route("/send_books", methods=["POST"])
def send_books():
    user_id: str = request.json.get("user_id")
    order_id: str = request.json.get("order_id")
    s = seller.Seller()
    try:
        code, message = s.send_books(user_id, order_id)
    finally:
        try:
            s.conn.close()  # 用后即弃
        except Exception:
            pass
    return jsonify({"message": message}), code