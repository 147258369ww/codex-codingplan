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


@pytest.mark.asyncio
async def test_lifespan_populates_app_state():
    """Test that lifespan startup populates app.state correctly."""
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

    # Simulate lifespan startup by entering the context manager
    async with app.router.lifespan_context(app):
        assert app.state.config is not None
        assert app.state.config == config
        assert app.state.client is not None
        assert app.state.converter is not None


@pytest.mark.asyncio
async def test_lifespan_calls_client_close():
    """Test that lifespan shutdown calls client.close()."""
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

    # Track if close was called
    close_called = False
    original_close = app.state.client.close if hasattr(app.state, 'client') else None

    # We need to enter the lifespan context to access the client
    async with app.router.lifespan_context(app):
        client = app.state.client
        # Patch the close method to track calls
        original_close_method = client.close

        async def tracked_close():
            nonlocal close_called
            close_called = True
            return await original_close_method()

        client.close = tracked_close

    # After exiting the context, close should have been called
    assert close_called, "client.close() was not called during lifespan shutdown"