def pytest_configure(config):
    for marker in ("unit", "api", "export"):
        config.addinivalue_line("markers", marker)
