from flask import Blueprint, request, jsonify
from be.model.buyer import Buyer

bp_admin = Blueprint("admin", __name__, url_prefix="/admin")


@bp_admin.route("/config", methods=["POST"])
def set_config():
    # Minimal test-only config setter
    timeout = request.json.get("order_timeout_seconds")
    if isinstance(timeout, int) and timeout > 0:
        Buyer.ORDER_TIMEOUT_SECONDS = timeout
        return jsonify({"message": "ok"}), 200
    return jsonify({"message": "invalid timeout"}), 401
