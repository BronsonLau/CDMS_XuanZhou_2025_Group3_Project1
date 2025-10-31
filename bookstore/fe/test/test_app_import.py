def test_app_imports():
    # 仅导入模块，覆盖 be/app.py 的顶层逻辑
    import importlib
    mod = importlib.import_module('be.app')
    assert hasattr(mod, '__name__')
