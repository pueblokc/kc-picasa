"""KC fork tests: register the `slow` marker (real model download)."""


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: downloads a real model or does heavy work; deselect with -m 'not slow'"
    )
