import requests
from urllib.parse import urljoin
from fe import conf


def test_admin_config_invalid():
    # 缺失或非法的 order_timeout_seconds 应返回 401
    url = urljoin(conf.URL, "admin/config")
    r1 = requests.post(url, json={})
    assert r1.status_code == 401
    r2 = requests.post(url, json={"order_timeout_seconds": -1})
    assert r2.status_code == 401
