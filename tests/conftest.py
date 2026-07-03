import pytest


def pytest_addoption(parser):
    """Add an explicit e2e opt-in so normal pytest runs stay fast and local."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="run optional e2e tests that create temporary DuckDB assets",
    )


def pytest_collection_modifyitems(config, items):
    """Make --e2e select e2e tests without repeating the tests/e2e path."""
    if config.getoption("--e2e"):
        selected = [item for item in items if "e2e" in item.keywords]
        deselected = [item for item in items if "e2e" not in item.keywords]
        config.hook.pytest_deselected(items=deselected)
        items[:] = selected
        return

    skip_e2e = pytest.mark.skip(reason="use --e2e to run optional e2e tests")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)
