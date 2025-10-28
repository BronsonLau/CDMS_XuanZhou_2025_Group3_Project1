import json
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict, Any

from be.model import db_conn
from be.model import mongo_store
from be.model import store_mongo
from pymongo.errors import OperationFailure


@dataclass
class Filter:
    isbn: Optional[str] = None
    pages: List[Optional[int]] = None  # [from, to]
    price: List[Optional[int]] = None  # [from, to] (cents)
    publish_date: List[Optional[int]] = None  # [from, to] (year)
    stock_level: List[Optional[int]] = None  # [from, to]
    store_id: Optional[str] = None

    def __post_init__(self):
        if self.pages is None:
            self.pages = [None, None]
        if self.price is None:
            self.price = [None, None]
        if self.publish_date is None:
            self.publish_date = [None, None]
        if self.stock_level is None:
            self.stock_level = [None, None]


class Search(db_conn.DBConn):
    """Search backed by MongoDB inventory collection.

    - Reads from collection "inventory" which stores redundant fields:
      title, author, isbn, pub_year, pages, price, stock_level.
    - Keeps an inherited SQLite connection so existing view code can safely
      call s.conn.close() without AttributeError during migration.
    """

    def __init__(self):
        super().__init__()
        self.mongo_db = mongo_store.get_db()
        self.col_inventory = self.mongo_db["inventory"]
        # Best-effort ensure indexes, including text index if supported
        try:
            store_mongo.ensure_indexes(self.mongo_db)
        except Exception:
            pass

    def _match_keyword(self, bi: Dict[str, Any], keyword: str) -> bool:
        # Keep a fallback in-memory match for fields stored only inside book_info
        if not keyword:
            return True
        kw = keyword.lower()
        fields = [
            bi.get("title", ""),
            bi.get("author", ""),
            bi.get("publisher", ""),
            bi.get("isbn", ""),
            bi.get("tags", ""),
            bi.get("content", ""),  # 目录/内容
            bi.get("book_intro", ""),
            bi.get("catalog", ""),
        ]
        blob = "\n".join([str(x) for x in fields]).lower()
        return kw in blob

    def _add_range(self, q: Dict[str, Any], field: str, bounds: List[Optional[int]]):
        if not bounds:
            return
        lo, hi = bounds[0], bounds[1]
        if lo is not None or hi is not None:
            cond: Dict[str, Any] = {}
            if lo is not None:
                try:
                    cond["$gte"] = int(lo)
                except Exception:
                    pass
            if hi is not None:
                try:
                    cond["$lte"] = int(hi)
                except Exception:
                    pass
            if cond:
                q[field] = cond

    def search(self, keyword: str, filter: Filter) -> Tuple[int, str, List[Dict[str, Any]]]:
        kw = (keyword or "").strip()
        # Build base query without keyword so we can try text->regex fallbacks cleanly
        q_base: Dict[str, Any] = {}

        # store_id
        if filter and filter.store_id:
            q_base["store_id"] = filter.store_id

        # exact ISBN
        if filter and filter.isbn:
            q_base["isbn"] = str(filter.isbn)

        # numeric ranges
        if filter:
            self._add_range(q_base, "stock_level", filter.stock_level)
            self._add_range(q_base, "pages", filter.pages)
            self._add_range(q_base, "price", filter.price)
            # publish_date in SQL version maps to pub_year here
            self._add_range(q_base, "pub_year", filter.publish_date)

        # Projection keeps book_info for fallback keyword match
        projection = {
            "_id": 0,
            "store_id": 1,
            "book_id": 1,
            "book_info": 1,
            "stock_level": 1,
            "title": 1,
            "author": 1,
            "isbn": 1,
            "price": 1,
            "pages": 1,
            "pub_year": 1,
        }

        # Helpers
        def _regex_query() -> Dict[str, Any]:
            # For robustness, when falling back from $text we avoid pushing keyword to Mongo.
            # We query by base filters only and apply keyword matching in Python over
            # title/author/isbn/publisher/tags/content/book_intro/catalog.
            return dict(q_base)

        def _text_query() -> Dict[str, Any]:
            if not kw:
                return dict(q_base)
            q = dict(q_base)
            q["$text"] = {"$search": kw}
            return q

        def _safe_int(v: Any, default: int = 0) -> int:
            try:
                return int(v)
            except Exception:
                return default

        def _collect_from_cursor(cursor_iter, require_kw_match: bool) -> List[Dict[str, Any]]:
            results: List[Dict[str, Any]] = []
            for doc in cursor_iter:
                store_id = doc.get("store_id")
                book_id = doc.get("book_id")
                stock_level = _safe_int(doc.get("stock_level", 0), 0)
                title = doc.get("title")
                author = doc.get("author")
                isbn = doc.get("isbn")
                price = doc.get("price")
                # keep pages/pub_year only for potential future filters; not returned

                # Fallback keyword match for fields inside JSON
                try:
                    bi = json.loads(doc.get("book_info") or "{}")
                except Exception:
                    bi = {}

                if require_kw_match and kw:
                    # ensure fallback keyword covers publisher/tags/content/book_intro/catalog as well
                    if not self._match_keyword(
                        {
                            "title": title,
                            "author": author,
                            "publisher": bi.get("publisher"),
                            "isbn": isbn,
                            "tags": bi.get("tags"),
                            "content": bi.get("content"),
                            "book_intro": bi.get("book_intro"),
                            "catalog": bi.get("catalog"),
                        },
                        kw,
                    ):
                        continue

                results.append(
                    {
                        "store_id": store_id,
                        "book_id": book_id,
                        "title": title,
                        "author": author,
                        "price": price,
                        "isbn": isbn,
                        "stock_level": stock_level,
                    }
                )
            return results

        # Main query path with robust fallbacks
        try:
            cursor = None
            used_text = False
            if kw:
                try:
                    # Try text search first; if any OperationFailure occurs, fallback to regex unconditionally
                    cursor = self.col_inventory.find(_text_query(), projection=projection).sort(
                        [("title", 1), ("book_id", 1)]
                    )
                    used_text = True
                except OperationFailure:
                    cursor = self.col_inventory.find(_regex_query(), projection=projection).sort(
                        [("title", 1), ("book_id", 1)]
                    )
            if cursor is None:
                cursor = self.col_inventory.find(_regex_query(), projection=projection).sort(
                    [("title", 1), ("book_id", 1)]
                )
            # If we used text search, we trust Mongo's match and do not require extra Python kw check.
            results = _collect_from_cursor(cursor, require_kw_match=not used_text)
            return 200, "ok", results
        except Exception as e:
            # Final safety net: base query without sort, then in-Python keyword check.
            # If even this fails, propagate as 528 to satisfy the "unexpected exception" unit test.
            try:
                cursor = self.col_inventory.find(_regex_query(), projection=projection)
                results = _collect_from_cursor(cursor, require_kw_match=True)
                return 200, "ok", results
            except Exception:
                return 528, str(e), []
