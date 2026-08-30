import pytest


def pytest_collection_modifyitems(items):
    """Auto-apply the 'integration' marker to every test collected from this directory."""
    for item in items:
        if "tests/integration" in str(item.fspath).replace("\\", "/"):
            item.add_marker(pytest.mark.integration)
