from be.model import search_mongo as search

# Back-compat: expose Search/Filter at module level for monkeypatch in tests
Search = search.Search
Filter = search.Filter
from flask import Blueprint
from flask import request
from flask import jsonify

bp_search = Blueprint("search", __name__, url_prefix="/search")


@bp_search.route("/keyword", methods=["POST"])
def search_books():
    s = Search()
    body = request.get_json(silent=True) or {}
    keyword = body.get("keyword") or ""

    f = Filter()
    raw_filter = body.get("filter") or {}
    # defensive get with defaults
    f.isbn = raw_filter.get("isbn")
    f.pages[0] = raw_filter.get("pages_from")
    f.pages[1] = raw_filter.get("pages_to")
    f.price[0] = raw_filter.get("price_from")
    f.price[1] = raw_filter.get("price_to")
    f.publish_date[0] = raw_filter.get("publish_date_from")
    f.publish_date[1] = raw_filter.get("publish_date_to")
    f.stock_level[0] = raw_filter.get("stock_from")
    f.stock_level[1] = raw_filter.get("stock_to")
    f.store_id = raw_filter.get("store_id")

    try:
        code, message, results = s.search(keyword, f)
    finally:
        # allow tests to monkeypatch a close that raises; fall back to conn.close
        try:
            if hasattr(s, "close"):
                s.close()
            elif hasattr(s, "conn") and hasattr(s.conn, "close"):
                s.conn.close()
        except Exception:
            # swallow close errors by design
            pass

    # simple pagination support (optional)
    page = int(body.get("page") or 1)
    size = int(body.get("size") or 20)
    if page < 1:
        page = 1
    if size < 1:
        size = 20
    start = (page - 1) * size
    paged = results[start : start + size]

    return jsonify({"message": message, "count": len(results), "results": paged}), code