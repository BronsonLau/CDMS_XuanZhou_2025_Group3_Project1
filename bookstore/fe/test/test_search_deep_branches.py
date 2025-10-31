import json
from be.model.search_mongo import Search, Filter
from be.model import mongo_store


def _insert_store_row(store_id: str, book_id: str, book_info: dict, stock: int):
	payload = json.dumps(book_info)
	inv = mongo_store.get_db()["inventory"]
	inv.delete_one({"store_id": store_id, "book_id": book_id})
	inv.insert_one(
		{
			"store_id": store_id,
			"book_id": book_id,
			"book_info": payload,
			"stock_level": int(stock),
			"title": book_info.get("title"),
			"author": book_info.get("author"),
			"isbn": book_info.get("isbn"),
			"pub_year": book_info.get("pub_year"),
			"pages": book_info.get("pages"),
			"price": book_info.get("price"),
		}
	)


def test_search_non_numeric_ranges_and_edges():
	# 插入非数字 pages/price/pub_year 到 book_info，冗余字段置空；仅 stock_level 过滤应命中
	_insert_store_row(
		"st_sd1",
		"bk_na",
		{"id": "bk_na", "title": "Edge", "author": "Au", "isbn": "X", "pages": "N/A", "price": "?", "pub_year": "???"},
		7,
	)

	s = Search()
	f = Filter(store_id="st_sd1")
	# 仅设置 stock_level，非数字的 pages/price/pub_year 不参与范围过滤
	f.stock_level = [5, 10]
	code, msg, rows = s.search("edge", f)
	assert code == 200 and any(r.get("book_id") == "bk_na" for r in rows)

	# 将 stock_level 上界调低，触发剔除（应返回空）
	f.stock_level = [None, 5]
	code, msg, rows = s.search("edge", f)
	assert code == 200 and len(rows) == 0


def test_search_unexpected_exception_returns_528(monkeypatch):
	s = Search()
	def boom(*a, **k):
		raise Exception("unexpected boom")
	monkeypatch.setattr(s.col_inventory, "find", lambda *a, **k: boom())
	code, msg, rows = s.search("kw", Filter())
	assert code == 528 and rows == [] and "boom" in msg


def test_search_json_fallback_with_store_and_keyword():
	# Mongo 查询将关键词下推到 title/author/isbn；为覆盖该路径，这里在冗余字段中提供 title
	bi = {"publisher": "Zeta Store", "author": "Au", "isbn": "JE-1"}
	inv = mongo_store.get_db()["inventory"]
	inv.delete_one({"store_id": "stx", "book_id": "bk1"})
	inv.insert_one({
		"store_id": "stx",
		"book_id": "bk1",
		"book_info": json.dumps(bi),
		"stock_level": 3,
		"title": "Zeta Store",
		"author": None,
		"isbn": None,
		"pub_year": None,
		"pages": None,
		"price": None,
	})

	s = Search()
	f = Filter(store_id="stx")
	code, msg, rows = s.search("Zeta", f)
	assert code == 200 and any(r.get("book_id") == "bk1" for r in rows)


def test_search_minimal_data_with_stock_range():
	# 最小字段的记录，依靠 stock_level 范围过滤命中
	inv = mongo_store.get_db()["inventory"]
	inv.delete_one({"store_id": "sty", "book_id": "bk2"})
	inv.insert_one({
		"store_id": "sty",
		"book_id": "bk2",
		"book_info": "{}",
		"stock_level": 6,
		"title": None,
		"author": None,
		"isbn": None,
		"pub_year": None,
		"pages": None,
		"price": None,
	})

	s = Search()
	f = Filter(store_id="sty")
	f.stock_level = [5, 10]
	code, msg, rows = s.search("", f)
	assert code == 200 and len(rows) == 1 and rows[0].get("stock_level") == 6

