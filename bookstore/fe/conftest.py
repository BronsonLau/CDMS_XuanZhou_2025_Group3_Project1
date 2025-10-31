import requests
import threading
from urllib.parse import urljoin
from be import serve
from be.serve import init_completed_event
from fe import conf

thread: threading.Thread = None


# 修改这里启动后端程序，如果不需要可删除这行代码
def run_backend():
    # rewrite this if rewrite backend
    serve.be_run()


def pytest_configure(config):
    global thread
    print("frontend begin test")
    thread = threading.Thread(target=run_backend)
    thread.start()
    init_completed_event.wait()
    # Global Mongo cleanup for tests (idempotent, best-effort)
    try:
        from be.model import mongo_store as _ms

        db = _ms.get_db()
        for _col in [
            "user",
            "stores",
            "inventory",
            "orders",
            "order_details",
            "order_status",
        ]:
            try:
                db[_col].delete_many({})
            except Exception:
                pass
    except Exception:
        # Mongo might be unavailable in some environments; ignore cleanup errors
        pass


def pytest_unconfigure(config):
    url = urljoin(conf.URL, "shutdown")
    requests.get(url)
    thread.join()
    print("frontend end test")
