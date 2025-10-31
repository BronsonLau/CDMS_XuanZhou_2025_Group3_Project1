import os
import random
import base64
import simplejson as json
from be.model import mongo_store


def _ensure_book_db(col_name: str, sample_size: int = 200):
    """Ensure MongoDB collection exists with at least `sample_size` deterministic rows.

    - If collection already has >= sample_size docs, do nothing.
    - Otherwise, upsert deterministic rows with ids bk_00000..bk_{sample_size-1}.
    - Create a unique index on `id` for fast lookup and to avoid duplicates.
    """
    db = mongo_store.get_db()
    col = db[col_name]
    try:
        col.create_index("id", unique=True)
    except Exception:
        pass
    try:
        if col.estimated_document_count() >= sample_size:
            return
    except Exception:
        # if estimation fails, continue to upsert
        pass

    for i in range(sample_size):
        bid = f"bk_{i:05d}"
        doc = {
            "id": bid,
            "title": f"Sample Book {i}",
            "author": "Author",
            "publisher": "Publisher",
            "original_title": "",
            "translator": "",
            "pub_year": "2024",
            # 覆盖测试用页数范围 [120, 350]
            "pages": 120 + (i % 300),
            "price": 1000 + (i % 500),  # cents
            "currency_unit": "CNY",
            "binding": "paperback",
            "isbn": f"9780000{i:05d}",
            "author_intro": "",
            "book_intro": "",
            "content": "",
            "tags": ["sample", "fiction"],
            "picture": None,
        }
        try:
            col.update_one({"id": bid}, {"$setOnInsert": doc}, upsert=True)
        except Exception:
            # ignore sporadic duplicate races in parallel test runs
            pass


class Book:
    id: str
    title: str
    author: str
    publisher: str
    original_title: str
    translator: str
    pub_year: str
    pages: int
    price: int
    currency_unit: str
    binding: str
    isbn: str
    author_intro: str
    book_intro: str
    content: str
    tags: list[str]
    pictures: list[bytes]

    def __init__(self):
        self.tags = []
        self.pictures = []


class BookDB:
    def __init__(self, large: bool = False):
        # Use Mongo collections for small/large datasets
        self.db = mongo_store.get_db()
        self.col_name_small = "bookdb_small"
        self.col_name_large = "bookdb_large"
        try:
            _ensure_book_db(self.col_name_small)
            _ensure_book_db(self.col_name_large)
        except Exception:
            pass
        self.col = self.db[self.col_name_large if large else self.col_name_small]
        # For small dataset used by unit tests, restrict to synthetic ids (bk_*) to ensure determinism
        self._synthetic_only = not large

    def get_book_count(self):
        q = {"id": {"$regex": "^bk_"}} if self._synthetic_only else {}
        return self.col.count_documents(q)

    def get_book_info(self, start, size) -> list[Book]:
        books: list[Book] = []
        q = {"id": {"$regex": "^bk_"}} if self._synthetic_only else {}
        cursor = (
            self.col.find(q, projection=None)
            .sort([("id", 1)])
            .skip(int(start))
            .limit(int(size))
        )
        for d in cursor:
            b = Book()
            b.id = d["id"]
            b.title = d["title"]
            b.author = d["author"]
            b.publisher = d["publisher"]
            b.original_title = d["original_title"]
            b.translator = d["translator"]
            b.pub_year = d["pub_year"]
            b.pages = d["pages"]
            b.price = d["price"]
            b.currency_unit = d["currency_unit"]
            b.binding = d["binding"]
            b.isbn = d["isbn"]
            b.author_intro = d["author_intro"]
            b.book_intro = d["book_intro"]
            b.content = d["content"]
            b.tags = list(d.get("tags") or [])
            b.pictures = []
            picture = d.get("picture")
            for _ in range(0, random.randint(0, 9)):
                if picture is not None:
                    b.pictures.append(base64.b64encode(picture).decode("utf-8"))
            books.append(b)
        return books
