# codex-proxy/tests/test_main.py
"""Tests for the main application entry point."""

import io
import logging
import re
import sys

import pytest
from fastapi.testclient import TestClient
from logging.handlers import TimedRotatingFileHandler

from codex_proxy.config import Config, ServerConfig, CodingPlanConfig, LoggingConfig
from codex_proxy.logging_utils import ConsoleFormatter
from codex_proxy.main import configure_logging, create_app


@pytest.fixture(autouse=True)
def restore_logging_state():
    root_logger = logging.getLogger()
    console_logger = logging.getLogger("codex_proxy.console")

    original_state = {
        root_logger: {
            "level": root_logger.level,
            "propagate": root_logger.propagate,
            "disabled": root_logger.disabled,
            "handlers": list(root_logger.handlers),
        },
        console_logger: {
            "level": console_logger.level,
            "propagate": console_logger.propagate,
            "disabled": console_logger.disabled,
            "handlers": list(console_logger.handlers),
        },
    }

    yield

    for logger, state in original_state.items():
        current_handlers = list(logger.handlers)
        for handler in current_handlers:
            logger.removeHandler(handler)
            if handler not in state["handlers"]:
                try:
                    handler.flush()
                except Exception:
                    pass
                try:
                    handler.close()
                except Exception:
                    pass

        logger.setLevel(state["level"])
        logger.propagate = state["propagate"]
        logger.disabled = state["disabled"]

        for handler in state["handlers"]:
            logger.addHandler(handler)


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


def test_configure_logging_closes_replaced_handlers(tmp_path):
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

    class TrackingFileHandler(TimedRotatingFileHandler):
        def __init__(self, filename):
            super().__init__(filename, when="midnight", interval=1, backupCount=1, encoding="utf-8")
            self.closed_called = False

        def close(self):
            self.closed_called = True
            super().close()

    class TrackingStreamHandler(logging.StreamHandler):
        def __init__(self):
            super().__init__(io.StringIO())
            self.closed_called = False

        def close(self):
            self.closed_called = True
            super().close()

    root_logger = logging.getLogger()
    console_logger = logging.getLogger("codex_proxy.console")

    old_file_handler = TrackingFileHandler(tmp_path / "old.log")
    old_console_handler = TrackingStreamHandler()
    root_logger.addHandler(old_file_handler)
    console_logger.addHandler(old_console_handler)

    configure_logging(config, log_dir=tmp_path, console_stream=io.StringIO())

    assert old_file_handler.closed_called is True
    assert old_console_handler.closed_called is True


def test_console_formatter_includes_exception_text():
    formatter = ConsoleFormatter(use_color=False)

    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="codex_proxy.console",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed request",
            args=(),
            exc_info=sys.exc_info(),
        )

    formatted = formatter.format(record)

    assert "failed request" in formatted
    assert "ValueError: boom" in formatted
    assert "Traceback" in formatted


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


def test_validation_errors_log_console_summary_and_file_details(tmp_path):
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
    client = TestClient(create_app(config))

    response = client.post("/v1/responses", json={})

    assert response.status_code == 422

    console_output = stream.getvalue()
    request_id_match = re.search(r"req_[0-9a-f]{4}", console_output)
    assert request_id_match is not None
    request_id = request_id_match.group(0)

    file_output = (tmp_path / "codex-proxy.log").read_text(encoding="utf-8")

    assert f"{request_id}  validation_failed status=422" in console_output
    assert "validation.errors" in file_output
    assert "validation.body" in file_output
    assert request_id in file_output


def test_middleware_logs_generic_request_lifecycle_for_health_and_404(tmp_path):
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
    client = TestClient(create_app(config))

    health_response = client.get("/health")
    missing_response = client.get("/missing")

    assert health_response.status_code == 200
    assert missing_response.status_code == 404

    file_output = (tmp_path / "codex-proxy.log").read_text(encoding="utf-8")

    assert re.search(
        r"http\.request\.started request_id=req_[0-9a-f]{4} method=GET path=/health",
        file_output,
    )
    assert re.search(
        r"http\.request\.completed request_id=req_[0-9a-f]{4} method=GET path=/health status=200",
        file_output,
    )
    assert re.search(
        r"http\.request\.started request_id=req_[0-9a-f]{4} method=GET path=/missing",
        file_output,
    )
    assert re.search(
        r"http\.request\.completed request_id=req_[0-9a-f]{4} method=GET path=/missing status=404",
        file_output,
    )
