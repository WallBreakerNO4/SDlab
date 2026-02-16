"""烟雾测试 - 验证基础环境和依赖正常工作"""


def test_smoke():
    assert True


def test_dependencies_available():
    import requests
    import websocket
    import dotenv

    assert requests is not None
    assert websocket is not None
    assert dotenv is not None
