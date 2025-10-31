import runpy
import sys
from unittest.mock import patch


def test_app_main_guard_calls_be_run():
    # 覆盖 be/app.py 的 __main__ 分支，但不提前导入 be.app，避免 runpy 的 RuntimeWarning
    with patch("be.serve.be_run") as mocked:
        # 确保 'be.app' 不在 sys.modules 中（可能被其他测试或补丁留存）
        sys.modules.pop("be.app", None)
        runpy.run_module("be.app", run_name="__main__")
        mocked.assert_called_once()
