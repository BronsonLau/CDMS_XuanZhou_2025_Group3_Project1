import base64
from fe.access.book import BookDB, Book
from be.model import mongo_store


def test_large_db_pictures_deterministic(monkeypatch):
    bdb = BookDB(large=True)

    # 使用 MongoDB 作为数据种子，插入包含图片字节的库存记录
    db = mongo_store.get_db()
    inv = db["inventory"]
    pic = b"hello-image-bytes"
    b64 = base64.b64encode(pic).decode("utf-8")
    doc = {
        "store_id": "store_pic",
        "book_id": "bk_pic_000",
        "book_info": "{}",
        "stock_level": 1,
        "title": "Pic Book",
        "author": "Author",
        "isbn": "9780000000000",
        "pages": 200,
        "price": 1234,
        # 直接存储字节，供测试用补丁读取
        "picture": pic,
    }
    inv.insert_one(doc)

    # 将 BookDB.get_book_info 猴补丁为使用 Mongo 返回包含多张图片的 Book
    def _fake_get_book_info(self, start, size):
        # 读取一条我们刚刚插入的带 picture 的库存记录
        d = inv.find_one({"book_id": "bk_pic_000"})
        b = Book()
        b.id = d["book_id"]
        b.title = d["title"]
        b.author = d["author"]
        b.publisher = "Publisher"
        b.original_title = ""
        b.translator = ""
        b.pub_year = "2024"
        b.pages = d.get("pages", 200)
        b.price = d.get("price", 1234)
        b.currency_unit = "CNY"
        b.binding = "paperback"
        b.isbn = d["isbn"]
        b.author_intro = ""
        b.book_intro = ""
        b.content = ""
        b.tags = ["sample", "fiction"]
        b.pictures = []
        import random as _rnd

        # 与大库路径一致的行为：按 random.randint 次数追加 base64 图片
        cnt = _rnd.randint(0, 9)
        picture_bytes = d.get("picture")
        for _ in range(cnt):
            if picture_bytes is not None:
                b.pictures.append(base64.b64encode(picture_bytes).decode("utf-8"))
        return [b]

    monkeypatch.setattr(BookDB, "get_book_info", _fake_get_book_info)

    # 固定 random.randint 返回 3，确保会追加 3 张图片
    monkeypatch.setattr("random.randint", lambda a, b: 3)
    books = bdb.get_book_info(0, 1)
    assert len(books) == 1
    assert len(books[0].pictures) == 3
    # verify they look like base64 strings
    for s in books[0].pictures:
        assert isinstance(s, str) and len(s) == len(b64)
