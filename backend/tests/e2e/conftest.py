import pytest


def pytest_collection_modifyitems(items):
    """Auto-apply the 'e2e' marker to every test collected from this directory."""
    for item in items:
        if "tests/e2e" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.e2e)
