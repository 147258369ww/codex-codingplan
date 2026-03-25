# codex-proxy/tests/conftest.py
"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def mock_api_key(monkeypatch):
    """Set mock API key for tests.

    This fixture provides a consistent way to set the CODING_PLAN_API_KEY
    environment variable for tests that need it. Tests can use it by adding
    'mock_api_key' as a parameter to their test function.

    Example:
        def test_something(mock_api_key):
            # CODING_PLAN_API_KEY is now set to "test-api-key"
            ...
    """
    monkeypatch.setenv("CODING_PLAN_API_KEY", "test-api-key")