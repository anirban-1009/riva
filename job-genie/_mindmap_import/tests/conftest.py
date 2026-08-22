from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def mock_sleep():
    """Globally patch time.sleep to speed up tests."""
    with patch("time.sleep", return_value=None):
        yield
