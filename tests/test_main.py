# codex-proxy/tests/test_main.py
"""Tests for the main application entry point."""

import pytest
from codex_proxy.main import create_app
from codex_proxy.config import Config, ServerConfig, CodingPlanConfig, LoggingConfig


def test_create_app():
    """Test that create_app returns a FastAPI application."""
    config = Config(
        server=ServerConfig(host="127.0.0.1", port=8080),
        coding_plan=CodingPlanConfig(
            base_url="https://api.test.com/v1",
            api_key="test-key",
            model="test-model",
            timeout=30,
        ),
        logging=LoggingConfig(),
    )

    app = create_app(config)

    assert app is not None
    assert app.title == "Codex Proxy"


def test_app_has_routes():
    """Test that app has expected routes."""
    config = Config(
        server=ServerConfig(host="127.0.0.1", port=8080),
        coding_plan=CodingPlanConfig(
            base_url="https://api.test.com/v1",
            api_key="test-key",
            model="test-model",
            timeout=30,
        ),
        logging=LoggingConfig(),
    )

    app = create_app(config)
    routes = [route.path for route in app.routes]

    assert "/health" in routes
    assert "/v1/responses" in routes