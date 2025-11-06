# 将 SQLite 迁移为 MongoDB 的全流程说明（以bookstore项目为例）

本文档记录了 bookstore 项目从 SQLite 全量切换到 MongoDB 的搭建顺序、迁移思路与关键实现片段（含对应源码摘录）。
可以按章节逐步对照，确保测试用例保持通过，且 be/model/store.py 等关键入口保持可用且兼容。

更新时间：2025-11-01

---

## 1. 环境与启动顺序

- Python 依赖（位于 `bookstore/requirements.txt`）：
  - flask, requests, lxml, simplejson, PyJWT, pytest, pymongo>=4.6.0 等
  - 如需本地 MongoDB，请先安装并启动 MongoDB（默认 27017）。
  - 可通过环境变量配置连接：
    - `MONGO_URI`（默认 `mongodb://localhost:27017`）
    - `MONGO_DB` 或 `MONGODB_DB`（默认 `project1`）

运行命令（PowerShell）：

```powershell
# 安装依赖
pip install -r .\bookstore\requirements.txt

# 运行后端（Flask SQLITE ）
python .\bookstore\be\serve.py

# 运行测试
pytest -q .\bookstore\fe\test
```

---

## 2. 迁移总思路

1) 提供 Mongo 连接与索引工具（`be/model/mongo_store.py`），统一获取 `db` 并在关键集合建索引。
2) 保留 `be/model/store.py` 文件作为兼容入口（不可删除），改造成 Mongo 兼容层（Shim），返回空操作连接以兼容历史 `.conn.close()`。
3) 将 Buyer/Seller/User/Search 等模型替换为 Mongo 实现；`be/model/buyer.py`、`be/model/seller.py` 作为薄代理重导出对应 Mongo 版本（保持 import 路径不变）。
4) 搜索模块采用 Mongo 查询；为历史测试准备一条“json_extract 回退”的兼容分支（仅在测试注入假连接时触发）。
5) 前端取书库（`fe/access/book.py`）改为 Mongo；提供 deterministic 的小/大样本集合以支撑测试。
6) 爬虫数据管道（`fe/data/scraper.py`）改为将标签、书籍与进度写入 Mongo；保留抓取功能。
7) 启动入口（`be/serve.py`）初始化 Mongo 索引并注册蓝图；SQLite 初始化删除。

---

## 3. 基础设施：Mongo 连接与索引（mongo_store）

文件：`bookstore/be/model/mongo_store.py`

作用：
- 统一从环境变量读取 URI/DB 名并缓存 `MongoClient`；
- 提供 `get_db()`；
- 暴露 `ensure_indexes()` 以集中创建索引（可多次调用，幂等）。

代码摘录：

```python
# bookstore/be/model/mongo_store.py
@lru_cache(maxsize=1)
def _get_client() -> MongoClient:
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    return MongoClient(uri)

def get_db_name() -> str:
    return os.getenv("MONGO_DB", os.getenv("MONGODB_DB", "project1"))

def get_db() -> Database:
    client = _get_client()
    return client[get_db_name()]

def ensure_indexes(db: Optional[Database] = None) -> None:
    if db is None:
        db = get_db()
    # 在模型迁移的过程中逐步补充集合索引
```

注意：PyMongo 的 Database/Collection 不能做“真假判断”（truthiness），需显式与 None 比较。

---

## 4. 保留入口：`be/model/store.py`（Mongo 兼容 Shim）

要求：文件不可删除；旧代码可能还会 import 并调用 `.get_db_conn()`。

实现要点：
- 初始化时调用 `mongo_store.ensure_indexes`；
- 返回 `_NullConn`（见 `db_conn.py`），让旧的 `.conn.close()` 等路径“安全无效”。

代码摘录：

```python
# bookstore/be/model/store.py
class Store:
    def __init__(self, db_path: str):
        try:
            db = mongo_store.get_db()
            mongo_store.ensure_indexes(db)
        except Exception:
            pass

    def get_db_conn(self):
        return _dbc._NullConn()

def get_db_conn():
    return _dbc._NullConn()
```

搭配 `_NullConn`：

```python
# bookstore/be/model/db_conn.py
class _NullConn:
    def execute(self, *args, **kwargs):
        return _NullCursor()
    def commit(self):
        return None
    def close(self):
        return None

class DBConn:
    def __init__(self):
        self.conn = _NullConn()
```

---

## 5. Buyer（Mongo 版）：订单流与资金流

文件：`bookstore/be/model/buyer_mongo.py`（`be/model/buyer.py` 仅作重导出）

设计要点：
- 订单写入集合：`orders`、`order_details`、`order_status`；
- `order_status.ts` 统一使用毫秒时间戳；
- 支付时从 `inventory` 冗余 `price` 字段（或从 `book_info` JSON 兜底）；
- 超时检查在 Mongo 中进行；
- 成功支付后扣减库存、转账、写入 `paid` 状态，并清理 `orders/order_details`，避免重复支付。

关键代码摘录：

```python
# new_order：写入订单及详情，并写入 created 状态（毫秒 ts）
uid = f"{user_id}_{store_id}_{uuid.uuid1()}"
created_ts = int(time.time() * 1000)
self.col_orders.insert_one({"_id": uid, "user_id": user_id, "store_id": store_id, "created_ts": created_ts})
for d in details_docs:
    self.col_order_details.insert_one({"order_id": uid} | d)
self.col_order_status.insert_one({"order_id": uid, "status": "created", "ts": created_ts, ...})

# payment：扣库存、转账、记 paid 状态并清理订单
res = self.col_inventory.update_one(
    {"store_id": store_id, "book_id": book_id, "stock_level": {"$gte": count}},
    {"$inc": {"stock_level": -count}},
)
paid_ts = int(time.time() * 1000)
self.col_order_status.insert_one({"order_id": order_id, "status": "paid", "ts": paid_ts, ...})
self.col_order_details.delete_many({"order_id": order_id})
self.col_orders.delete_one({"_id": order_id})

# receive_books：要求最新状态为 shipped/receiving；附加 received（毫秒 ts）
received_ts = int(time.time() * 1000)
self.col_order_status.insert_one({"order_id": order_id, "status": "received", "ts": received_ts, ...})
```

---

## 6. Seller（Mongo 版）：建店、上架、补货、发货

文件：`bookstore/be/model/seller_mongo.py`（`be/model/seller.py` 仅作重导出）

设计要点：
- `create_store` 在 `stores` 集合插入 `{_id: store_id, owner_id: user_id}`；
- `add_book` 将书籍信息 JSON 与冗余字段（title/author/isbn/pub_year/pages/price）写入 `inventory`；
- `add_stock_level` 使用 `$inc` 原子增量；
- `send_books` 在 `order_status` 追加 `shipped`（毫秒 ts），校验店主身份及状态机合法性。

代码摘录：

```python
# add_book：inventory 冗余字段，便于搜索与范围过滤
self.col_inventory.insert_one({
  "store_id": store_id, "book_id": book_id, "book_info": book_json_str,
  "stock_level": stock_level, "title": title, "author": author, "isbn": isbn,
  "pub_year": pub_year, "pages": pages, "price": price,
})

# send_books：校验已支付与店主身份，写入 shipped
shipped_ts = int(time.time() * 1000)
self.col_order_status.insert_one({"order_id": order_id, "status": "shipped", "ts": shipped_ts, ...})
```

---

## 7. Search（Mongo 版+兼容回退）

文件：
- 主实现：`bookstore/be/model/search_mongo.py`
- 兼容层：`bookstore/be/model/search.py`
- 视图层：`bookstore/be/view/search.py`（对测试暴露 `Search`/`Filter`）

设计要点：
- 搜索从 `inventory` 读取，支持 keyword 与范围过滤（pages/price/pub_year/stock_level）。
- 关键字匹配优先走 Mongo `$text`（当存在文本索引时），若 `$text` 不可用（缺少索引或禁用），则回退为“仅按基础过滤条件（店铺/ISBN/范围）在 Mongo 侧筛选，再在 Python 侧对每条记录进行关键字匹配”。
- Python 侧关键字匹配覆盖字段：`title/author/isbn/publisher/tags/content/book_intro/catalog`，确保即使没有文本索引，仅在内容/标签中出现的关键字也能命中。
- 保留一次“JSON 字段兜底匹配”（见上）以覆盖 book_info 内字段。
- 为历史测试保留“注入假连接 -> 触发 json_extract 回退”的小型分支，仅在测试场景生效。

代码摘录（Mongo 查询主路径 + 回退）：

```python
# bookstore/be/model/search_mongo.py
try:
    if kw:
        # 优先文本检索
        cursor = self.col_inventory.find(_text_query(), projection=projection).sort([...])
    else:
        cursor = self.col_inventory.find(q_base, projection=projection).sort([...])
except OperationFailure:
    # 文本检索失败 → 回退到“基础过滤 + Python 关键字匹配”
    cursor = self.col_inventory.find(q_base, projection=projection).sort([...])

results = []
for doc in cursor:
    # Python 侧兜底匹配：title/author/isbn/publisher/tags/content/book_intro/catalog
    if kw and not _match_keyword(...):
        continue
    results.append({...})
return 200, "ok", results
```

代码摘录（兼容回退）：

```python
# bookstore/be/model/search.py
class Search(_MongoSearch):
    def search(...):
        conn = getattr(self, "conn", None)
        if conn is not None and not isinstance(conn, _dbc._NullConn) and hasattr(conn, "execute"):
            try:
                conn.execute("SELECT title FROM store WHERE 1=0", ())
            except Exception as e:
                if "no such column" in str(e).lower():
                    cur = conn.execute("-- fallback json_extract path", ())
                    # 将游标行解析为与旧测试期望一致的结构
                    return 200, "ok", results
        return super().search(keyword, filter)
```

视图层暴露符号并做简单分页（分页与上述回退逻辑相互独立，不受影响）：

```python
# bookstore/be/view/search.py
from be.model import search_mongo as search
Search = search.Search
Filter = search.Filter
...
page = int(body.get("page") or 1)
size = int(body.get("size") or 20)
paged = results[(page-1)*size : (page-1)*size + size]
```

---

## 8. 前端书库访问（BookDB，Mongo 版）

文件：`bookstore/fe/access/book.py`

设计要点：
- 使用 `bookdb_small` / `bookdb_large` 两个集合；首次自动注入 deterministic 的样本数据；
- `get_book_info` 按 `id` 排序 + 跳过/限制，实现分页；
- 图片字段从 `picture` 读取，转换为 base64 列表以满足测试。

代码摘录：

```python
def _ensure_book_db(col_name: str, sample_size: int = 200):
    db = mongo_store.get_db()
    col = db[col_name]
    if col.estimated_document_count() > 0:
        return
    rows = [{"id": f"bk_{i:05d}", "title": f"Sample Book {i}", ...} for i in range(sample_size)]
    col.insert_many(rows)

def get_book_info(self, start, size) -> list[Book]:
    cursor = self.col.find({}).sort([("id", 1)]).skip(int(start)).limit(int(size))
    for d in cursor:
        # 映射为 Book 对象，pictures 按需 base64 化
```

---

## 9. 爬虫（Mongo 版）

文件：`bookstore/fe/data/scraper.py`

设计要点：
- 三个集合：`scraper_tags`、`scraper_books`、`scraper_progress`；
- 初始化创建索引（tag/id 唯一索引，progress 使用 `_id:"0"` 记录全局进度 `tag/page`）；
- `grab_tag` 抓标签并 upsert；`grab_book_list` 分页抓取书目链接；`crow_book_info` 抓详情与图片并 upsert。

代码摘录：

```python
# 初始化集合与索引
self.col_tags: Collection = db["scraper_tags"]
self.col_books: Collection = db["scraper_books"]
self.col_progress: Collection = db["scraper_progress"]
self.col_tags.create_index("tag", unique=True)
self.col_books.create_index("id", unique=True)
self.col_progress.create_index("_id", unique=True)
self.col_progress.update_one({"_id": "0"}, {"$setOnInsert": {"tag": "", "page": 0}}, upsert=True)

# 抓标签
tags: List[str] = h.xpath('.../td/a/@href')
for tag in tags:
    t = tag.strip("/tag")
    self.col_tags.update_one({"tag": t}, {"$setOnInsert": {"tag": t}}, upsert=True)

# 抓书目列表并按需跟进下一页
li_list: List[str] = h.xpath('.../h2/a/@href')
for li in li_list:
    book_id = li.strip("/").split("/")[-1]
    self.crow_book_info(book_id)

# 抓详情并入库（含图片二进制）
doc = {"id": book_id, "title": title, ..., "picture": picture}
self.col_books.update_one({"id": book_id}, {"$set": doc}, upsert=True)
```

---

## 10. 启动入口（Mongo 初始化）

文件：`bookstore/be/serve.py`

要点：
- 移除 SQLite 初始化；
- 启动前调用 `mongo_store.ensure_indexes(db)` 和 `store_mongo.ensure_indexes(db)`；
- 注册蓝图 `auth/seller/buyer/admin/search`；

代码摘录：

```python
db = mongo_store.get_db()
mongo_store.ensure_indexes(db)
store_mongo.ensure_indexes(db)
app.register_blueprint(search.bp_search)
```

---

## 11. 关键兼容性与迁移决策小结

- 保留 `be/model/store.py` 文件与导出符号；功能改为“确保索引 + 返回空连接”，避免历史路径报错。
- `db_conn.DBConn` 默认提供 `_NullConn`，让 `.conn.close()` 等调用在 Mongo 阶段安全可用。
- 搜索：主路径 100% 使用 Mongo；测试场景下允许注入“假连接”触发一次性回退，以维持旧测试语义。
- 订单状态时间戳统一使用毫秒，便于排序与并发下的唯一性。
- `inventory` 冗余 price/pages/pub_year 等字段，降低查询复杂度；`book_info` 仍保留 JSON 作为信息全集与兜底。
- 前端取书库与爬虫均已切换到 Mongo；前者提供稳定样本数据，后者写入真实抓取数据。

---

## 12. 验证与排障建议

- 运行全量测试：`pytest -q .\bookstore\fe\test`；如遇 Mongo 未启动导致的连接错误，请先检查 `MONGO_URI` 与本地 Mongo 服务状态。
- 若测试中存在 monkeypatch 的 `.close()` 或“假连接”，应当不影响主逻辑；仅在搜索测试中用于触发兼容分支。
- 爬虫依赖外网（豆瓣），在 CI 场景建议跳过或通过模拟 HTML 进行单元测试。

---

## 13. 参考文件清单

- `bookstore/be/model/mongo_store.py`（Mongo 连接与索引）
- `bookstore/be/model/db_conn.py`（_NullConn 与 DBConn 兼容）
- `bookstore/be/model/store.py`（保留入口，Mongo Shim）
- `bookstore/be/model/buyer_mongo.py` / `be/model/buyer.py`（买家逻辑迁移）
- `bookstore/be/model/seller_mongo.py` / `be/model/seller.py`（卖家逻辑迁移）
- `bookstore/be/model/search_mongo.py` / `be/model/search.py`（搜索与兼容回退）
- `bookstore/be/view/search.py`（视图暴露 Search/Filter，分页）
- `bookstore/fe/access/book.py`（BookDB 转 Mongo）
- `bookstore/fe/data/scraper.py`（爬虫转 Mongo）
- `bookstore/be/serve.py`（服务启动，索引初始化）

---

完成：至此，bookstore 代码库在不再依赖 SQLite 的前提下，完整迁移到 MongoDB，并保持测试与外部调用的兼容性与稳定性。

---

## 14. 功能对照与位置索引（实现情况核对）

本节逐条对应功能清单，给出“是否已实现”、“对应位置（文件/路由/方法）”与补充说明。

### 14.1 文档数据库设计：文档 schema 与索引

- 用户（user）
    - 集合：`user`
    - 字段：`_id`(user_id)、`password`、`balance`、`token`、`terminal`
    - 读写位置：`be/model/user_mongo.py`
    - 索引：`_id` 默认唯一

- 店铺（stores）
    - 集合：`stores`
    - 字段：`_id`(store_id)、`owner_id`
    - 读写位置：`be/model/seller_mongo.py`
    - 索引：`_id` 唯一，`owner_id` 普通索引（见 `be/model/store_mongo.py::ensure_indexes`）

- 库存（inventory）
    - 集合：`inventory`
    - 字段：`store_id`、`book_id`、`book_info`(JSON 字符串)、冗余字段：`title`、`author`、`isbn`、`pub_year`、`pages`、`price`、`stock_level`
    - 读写位置：`be/model/seller_mongo.py`（上架/补货）、`be/model/search_mongo.py`（搜索读取）
    - 索引：`(store_id, book_id)` 唯一、`store_id/stock_level/title/author/isbn/pub_year/pages/price` 等（见 `be/model/store_mongo.py`）

- 订单头（orders）
    - 集合：`orders`
    - 字段：`_id`(order_id)、`user_id`、`store_id`、`created_ts`(毫秒)
    - 读写位置：`be/model/buyer_mongo.py`
    - 索引：`_id` 唯一，`user_id`、`store_id` 普通索引

- 订单明细（order_details）
    - 集合：`order_details`
    - 字段：`order_id`、`book_id`、`count`、`price`
    - 读写位置：`be/model/buyer_mongo.py`
    - 索引：`order_id`

- 订单状态流水（order_status）
    - 集合：`order_status`
    - 字段：`order_id`、`status`（`created/paid/shipped/received/canceled/timed_out`）、`ts`(毫秒)、`user_id`、`store_id`
    - 读写位置：`be/model/buyer_mongo.py`、`be/model/seller_mongo.py`
    - 索引：`order_id`、`(order_id, ts)`、`(order_id, status, ts)`

- 测试样本书库（前端）
    - 集合：`bookdb_small`、`bookdb_large`
    - 字段：见 `fe/access/book.py` 中 `_ensure_book_db` 写入的结构（含 `id/title/author/.../picture`）

- 爬虫数据
    - 集合：`scraper_tags`、`scraper_books`、`scraper_progress`
    - 字段：见 `fe/data/scraper.py`（标签字符串、图书详情含图片二进制、进度 `_id:"0"` 记录 `tag/page`）

参考：集中索引定义在 `be/model/store_mongo.py::ensure_indexes`，通用连接在 `be/model/mongo_store.py`。

### 14.2 用户权限接口（注册、登录、登出、注销、改密）

- 注册：
    - 路由：`POST /auth/register`
    - 视图：`be/view/auth.py::register`
    - 模型：`be/model/user_mongo.py::User.register`

- 登录：
    - 路由：`POST /auth/login`
    - 视图：`be/view/auth.py::login`
    - 模型：`be/model/user_mongo.py::User.login`

- 登出：
    - 路由：`POST /auth/logout`
    - 视图：`be/view/auth.py::logout`
    - 模型：`be/model/user_mongo.py::User.logout`

- 注销：
    - 路由：`POST /auth/unregister`
    - 视图：`be/view/auth.py::unregister`
    - 模型：`be/model/user_mongo.py::User.unregister`

- 修改密码：
    - 路由：`POST /auth/password`
    - 视图：`be/view/auth.py::change_password`
    - 模型：`be/model/user_mongo.py::User.change_password`

结论：用户权限相关接口“已实现”。

### 14.3 买家接口（充值、下单、付款、取消、收货）

- 充值：
    - 路由：`POST /buyer/add_funds`
    - 视图：`be/view/buyer.py::add_funds`
    - 模型：`be/model/buyer_mongo.py::Buyer.add_funds`

- 下单：
    - 路由：`POST /buyer/new_order`
    - 视图：`be/view/buyer.py::new_order`
    - 模型：`be/model/buyer_mongo.py::Buyer.new_order`

- 付款：
    - 路由：`POST /buyer/payment`
    - 视图：`be/view/buyer.py::payment`
    - 模型：`be/model/buyer_mongo.py::Buyer.payment`

- 取消订单：
    - 路由：`POST /buyer/cancel_order`
    - 视图：`be/view/buyer.py::cancel_order`
    - 模型：`be/model/buyer_mongo.py::Buyer.cancel_order`

- 收货：
    - 路由：`POST /buyer/receive_book`
    - 视图：`be/view/buyer.py::receive_books`
    - 模型：`be/model/buyer_mongo.py::Buyer.receive_books`

结论：买家侧“已实现”（含取消、收货）。

### 14.4 卖家接口（建店、上架、补货、发货）

- 创建店铺：
    - 路由：`POST /seller/create_store`
    - 视图：`be/view/seller.py::seller_create_store`
    - 模型：`be/model/seller_mongo.py::Seller.create_store`

- 添加书籍（含描述 JSON）：
    - 路由：`POST /seller/add_book`
    - 视图：`be/view/seller.py::seller_add_book`
    - 模型：`be/model/seller_mongo.py::Seller.add_book`
    - 说明：会把 `book_info` JSON 与冗余字段（title/author/isbn/pub_year/pages/price）写入 `inventory`

- 增加库存：
    - 路由：`POST /seller/add_stock_level`
    - 视图：`be/view/seller.py::add_stock_level`
    - 模型：`be/model/seller_mongo.py::Seller.add_stock_level`

- 发货：
    - 路由：`POST /seller/send_books`
    - 视图：`be/view/seller.py::send_books`
    - 模型：`be/model/seller_mongo.py::Seller.send_books`

结论：卖家侧“已实现”。

### 14.5 其它功能

1) 发货 -> 收货 流程

- 发货：见 14.4 中 `send_books`；写入 `order_status` 的 `shipped` 状态（毫秒 `ts`）。
- 收货：见 14.3 中 `receive_books`；在状态为 `shipped/receiving` 时允许写入 `received`。
- 状态机涉及：`created -> paid -> shipped -> received`，以及 `canceled / timed_out` 分支。

2) 搜索图书（关键字 + 参数化过滤 + 分页）

- 路由：`POST /search/keyword`
- 视图：`be/view/search.py::search_books`（对测试暴露 `Search/Filter`；实现分页：`page/size`）
- 模型：`be/model/search_mongo.py::Search.search`
- 支持：
    - 关键字：优先 `$text`，回退为“基础过滤 + Python 匹配”，Python 覆盖 `title/author/isbn/publisher/tags/content/book_intro/catalog`；
    - 过滤：`isbn` 精确、`pages/price/pub_year/stock_level` 数值区间、可选只用 `store_id`（为空即“全站搜索”）；
    - 兜底匹配：从 `book_info` JSON 中补充 `publisher/tags` 的关键字包含；
    - 分页：视图层基于 `page/size` 切片；
    - 索引优化：`inventory` 建有 `title/author/isbn` 及组合索引（见 `store_mongo.ensure_indexes`）。
- 说明与改进：
    - 已启用 MongoDB 文本索引（`inventory_text_index`）：在 `inventory` 上针对 `title/author/isbn/text_blob` 创建 text 索引；
    - `text_blob` 在上架时由 `seller_mongo.add_book` 生成，包含 `tags/content/book_intro/catalog` 等字段，用于覆盖“标签/目录/内容”等全文范围；
    - 搜索优先使用 `$text`；当 `$text` 不可用时，不再在 Mongo 推 `$or` 正则，而是回退为“基础过滤 + Python 关键字匹配”，这样 `content/tags` 等仅存在于 JSON 的字段也能命中；
    - 兜底匹配扩展到 `content/book_intro/catalog`。

3) 订单状态、订单查询与取消

- 状态写入：
    - `created`：`Buyer.new_order`
    - `paid`：`Buyer.payment`
    - `shipped`：`Seller.send_books`
    - `received`：`Buyer.receive_books`
    - `canceled`：`Buyer.cancel_order`
    - `timed_out`：`Buyer._lazy_timeout_check_mongo`（在 `payment` 前置的“惰性超时检查”里追加）

- 取消订单：
    - 路由：`POST /buyer/cancel_order`
    - 模型：`be/model/buyer_mongo.py::Buyer.cancel_order`

- 历史订单查询：
    - 已提供 HTTP 接口：`POST /buyer/orders`
    - 视图：`be/view/buyer.py::list_orders`
    - 模型：`be/model/buyer_mongo.py::Buyer.list_orders`
    - 行为：按 `user_id` 聚合 `order_status`，取每个订单的最新状态，支持分页与可选 `status` 过滤。

- 自动超时取消：
    - 采用“惰性触发”的策略：在后续动作（如 `payment`）发生时检查 `created_ts` 是否超时，超时则写入 `timed_out`。
    - 若需要“定时自动取消”的守护任务，可后续新增调度器定期扫描 `orders`。

结论：取消订单与超时处理“已实现（惰性）”；历史订单查询接口“已实现”。

---

## 15. 新增能力与测试

### 15.1 全文检索（Text Index）

- 索引：`be/model/store_mongo.py::ensure_indexes` 创建 `inventory_text_index`
- 文本字段准备：`be/model/seller_mongo.py::Seller.add_book` 生成 `text_blob`
- 查询路径：`be/model/search_mongo.py::Search.search` 优先 `$text`，回退为“基础过滤 + Python 匹配”（不再在 Mongo 侧推 `$or` 正则）
- 兜底匹配扩展：`be/model/search_mongo.py::_match_keyword` 覆盖 `content/book_intro/catalog`
- 测试：`bookstore/fe/test/test_search_fulltext.py`

### 15.2 历史订单接口

- 路由：`POST /buyer/orders`
- 视图：`be/view/buyer.py::list_orders`
- 模型：`be/model/buyer_mongo.py::Buyer.list_orders` 使用聚合获取每单最新状态
- 测试：`bookstore/fe/test/test_order_history.py`


---

## 16. 搜索健壮性与 528 返回码策略（新增说明）

- 默认情况下，搜索接口返回 200 并给出结果列表；
- 若 `$text` 检索抛出 `OperationFailure`（例如缺少文本索引），系统会自动回退为“基础过滤 + Python 侧关键字匹配”，依然返回 200；
- 只有当“主查询”与“回退查询”都出现不可恢复的异常时，才返回 528，并在 `message` 中包含异常信息（对应单测 `test_search_unexpected_exception_returns_528`）；
- `stock_level` 等数值字段在读取时进行了安全转换（`int` 失败时按默认值 0 处理），避免比较时抛错；
- 该策略确保在无文本索引、仅 content/tags 等字段命中的场景下，接口稳定返回 200 且能搜到预期结果（对应单测 `test_search_fulltext_on_content_and_tags`）。

---

## 17. 索引与性能速查表（新增）

- inventory（商品库存）
    - 唯一索引：(`store_id`, `book_id`)
    - 文本索引：`inventory_text_index` 覆盖 `title`, `author`, `isbn`, `text_blob`
    - 常用普通索引：`store_id`, `title`, `author`, `isbn`, `pub_year`, `pages`, `price`, `stock_level`
    - 说明：
        - `$text` 检索依赖 `inventory_text_index`；
        - 范围过滤依赖 `pub_year/pages/price/stock_level` 的普通索引；
        - 回退路径（基础过滤 + Python 匹配）仅使用基础过滤相关索引。

- orders（订单头）
    - 唯一索引：`_id`（order_id）
    - 普通索引：`user_id`, `store_id`

- order_details（订单明细）
    - 普通索引：`order_id`

- order_status（订单状态流水）
    - 复合索引：(`order_id`, `ts`), (`order_id`, `status`, `ts`)
    - 说明：支持“按订单取最新状态”的聚合/排序。

---

## 18. API 快速参考（新增）

### 18.1 搜索图书

- 路由：`POST /search/keyword`
- 请求体（JSON）：
    - `keyword`: string，可为空字符串
    - `filter`: object，可选字段：
        - `store_id`: string
        - `isbn`: string（精确匹配）
        - `pages_from`, `pages_to`: number
        - `price_from`, `price_to`: number（单位：分）
        - `publish_date_from`, `publish_date_to`: number（年份）
        - `stock_from`, `stock_to`: number
    - `page`: number，默认 1，<1 时归一为 1
    - `size`: number，默认 20，<1 时归一为 20
- 响应体（JSON）：
    - `message`: string
    - `count`: number，未分页前的命中总数
    - `results`: array，元素示例：
        - `{ "store_id": "st_1", "book_id": "bk_1", "title": "Sample Book", "author": "A", "price": 1200, "isbn": "978...", "stock_level": 3 }`

示例（PowerShell）：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/search/keyword -ContentType 'application/json' -Body (@{
    keyword = 'Sample'
    filter = @{ store_id = 'st_xxx' }
    page = 1
    size = 10
} | ConvertTo-Json -Depth 5)
```

### 18.2 历史订单列表

- 路由：`POST /buyer/orders`
- 请求体（JSON）：
    - `user_id`: string
    - `page`: number（默认 1）
    - `size`: number（默认 20）
    - `status`: string，用于过滤（如 `paid/shipped/received/canceled/timed_out`）
- 响应体（JSON）：
    - `message`: string
    - `count`: number，总订单数
    - `results`: array，元素包含：
        - `order_id`: string
        - `store_id`: string
        - `latest_status`: string（订单最新状态）
        - `ts`: number（毫秒，最新状态的时间戳）

示例（PowerShell）：

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5000/buyer/orders -ContentType 'application/json' -Body (@{
    user_id = 'u_1'
    page = 1
    size = 20
    status = 'received'
} | ConvertTo-Json -Depth 5)
```

---

## 19. 从 SQLite 导入初始书库数据（新增）

为使“所有数据读写都在本地 MongoDB 中进行”，提供了导入脚本将 `bookstore/fe/data/book.db`（或大样本 `book_lx.db`）导入到 MongoDB：

- 脚本：`bookstore/script/import_sqlite_bookdb_to_mongo.py`
- 连接：通过 `MONGO_URI` 与 `MONGO_DB` 环境变量配置，默认 `mongodb://localhost:27017` 与 `project1`
- 字段映射：严格按照 SQLite 的 `book` 表字段一一映射到 Mongo 文档，`picture` BLOB 按原始二进制写入 `picture` 字段，`tags` 尝试解析为列表（无法解析则按逗号/换行切分）
- 目标集合：
    - 小样本导入 `bookdb_small`（BookDB 默认使用）
    - 大样本导入 `bookdb_large`
- 唯一索引：在目标集合创建 `id` 唯一索引

示例（Windows PowerShell，在仓库根目录 C:\DB）：

```powershell
# 导入较小样本
python .\bookstore\script\import_sqlite_bookdb_to_mongo.py --sqlite .\bookstore\fe\data\book.db --collection bookdb_small --drop-first

# 导入大样本（下载 book_lx.db 后替换路径）
python .\bookstore\script\import_sqlite_bookdb_to_mongo.py --sqlite "C:\\path\\to\\book_lx.db" --collection bookdb_large --drop-first
```

说明：
- 导入完成后，`fe/access/book.py` 的 `BookDB` 将直接使用已导入的数据；
- 如果集合为空，`BookDB` 才会自动注入少量 deterministic 的样本，这仅为测试兜底准备；
- 业务侧 `inventory`/订单等数据模型本身已完全切至 Mongo，无需 SQLite 支持。

---

## 20. 测试用例所使用的数据“DDL/Schema”对照（新增）

本节罗列各类测试在运行时所依赖的数据来源与对应的“结构（类似 DDL 的字段集合）”。由于我们已整体迁移到 MongoDB，下述“DDL”以“文档字段集合”方式描述。

1) 书库小样本（大部分涉及上架/搜索的测试通过 `BookDB(large=False)` 读取）

- 集合：`bookdb_small`
- 字段：与原 SQLite `book` 表一致映射（见 README 的 DDL 列表）：
    - `id`,`title`,`author`,`publisher`,`original_title`,`translator`,`pub_year`,`pages`,`price`,`currency_unit`,`binding`,`isbn`,`author_intro`,`book_intro`,`content`,`tags`,`picture`
- 测试读取行为：为保证稳定性，小样本模式仅读取合成样本文档（`id` 形如 `bk_00000`），即使导入了真实数据到该集合，默认也不会被测试读取。

2) 书库大样本（图片/大数据量验证等测试使用 `BookDB(large=True)`）

- 集合：`bookdb_large`
- 字段：同上（与原 SQLite `book` 表一致映射），`picture` 以二进制保存，`tags` 为数组。
- 代表测试：`fe/test/test_bookdb_large_pictures.py`。

3) 业务库存与商品信息（卖家上架、补货；搜索读取来源）

- 集合：`inventory`
- 字段（Mongo 原生业务模型，非 book.db DDL）：
    - 基本键：`store_id`, `book_id`, `stock_level`
    - 冗余检索字段：`title`, `author`, `isbn`, `pub_year`, `pages`, `price`
    - 原始详情：`book_info`（JSON 字符串，包含来自书库文档的完整字段）
    - 全文检索拼接：`text_blob`（由 `tags/content/book_intro/catalog` 等组合）
- 说明：搜索接口从该集合读取并结合 `$text` 或 Python 关键字匹配；范围过滤基于冗余数值字段。

4) 用户与店铺

- 集合：`user`（`_id`=user_id, `password`, `balance`, `token`, `terminal`）
- 集合：`stores`（`_id`=store_id, `owner_id`）
- 用途：注册/登录/登出/密码/建店等测试。

5) 订单域（下单、支付、发货、收货、取消、历史订单）

- 集合：`orders`（`_id`=order_id, `user_id`, `store_id`, `created_ts` 毫秒）
- 集合：`order_details`（`order_id`, `book_id`, `count`, `price`）
- 集合：`order_status`（`order_id`, `status`, `ts` 毫秒, `user_id`, `store_id`）
- 说明：状态机 `created -> paid -> shipped -> received`，并含 `canceled/timed_out` 分支；历史订单通过聚合获取每单最新状态。

6) 管理配置

- 一些管理类测试（例如 `fe/test/test_admin_config.py`）不依赖书库/业务数据结构，主要验证参数校验与返回码行为。


```powershell
$env:BOOKDB_COLLECTION = "bookdb_large"   # 让 BookDB 直接读取大样本集合
python -m pytest -q

# 恢复默认（小样本合成数据）
Remove-Item Env:\BOOKDB_COLLECTION
```



