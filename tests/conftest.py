# codex-proxy/tests/conftest.py
"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture
def mock_api_key(monkeypatch):
    """Set mock API key for tests."""
    monkeypatch.setenv("CODING_PLAN_API_KEY", "test-api-key")