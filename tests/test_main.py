# codex-proxy/tests/test_main.py
"""Tests for the main application entry point."""

import io
import logging

import pytest
from logging.handlers import TimedRotatingFileHandler

from codex_proxy.config import Config, ServerConfig, CodingPlanConfig, LoggingConfig
from codex_proxy.logging_utils import ConsoleFormatter
from codex_proxy.main import configure_logging, create_app


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


def test_configure_logging_separates_console_and_file_handlers(tmp_path):
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

    stream = io.StringIO()

    configure_logging(config, log_dir=tmp_path, console_stream=stream)

    root_logger = logging.getLogger()
    console_logger = logging.getLogger("codex_proxy.console")

    assert root_logger.level == logging.DEBUG
    assert len(root_logger.handlers) == 1
    assert isinstance(root_logger.handlers[0], TimedRotatingFileHandler)
    assert root_logger.handlers[0].level == logging.DEBUG
    assert root_logger.handlers[0].baseFilename == str(tmp_path / "codex-proxy.log")
    assert root_logger.handlers[0].formatter._style._fmt == config.logging.format

    assert console_logger.propagate is False
    assert len(console_logger.handlers) == 1
    assert isinstance(console_logger.handlers[0], logging.StreamHandler)
    assert console_logger.handlers[0].stream is stream
    assert console_logger.handlers[0].level == logging.INFO
    assert isinstance(console_logger.handlers[0].formatter, ConsoleFormatter)


def test_configure_logging_writes_console_summary_to_console_logger_only(tmp_path):
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

    stream = io.StringIO()

    configure_logging(config, log_dir=tmp_path, console_stream=stream)

    console_logger = logging.getLogger("codex_proxy.console")
    file_logger = logging.getLogger("codex_proxy.router")
    file_path = tmp_path / "codex-proxy.log"

    console_logger.info("done  status=200", extra={"request_id": "req_test"})
    file_logger.info("file message")

    for handler in logging.getLogger().handlers:
        handler.flush()

    output = stream.getvalue()
    file_output = file_path.read_text(encoding="utf-8")

    assert "req_test" in output
    assert "done  status=200" in output
    assert "file message" not in output
    assert "file message" in file_output
    assert "done  status=200" not in file_output


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
