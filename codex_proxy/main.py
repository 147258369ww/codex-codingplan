"""FastAPI application entry point."""

import json
import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TextIO

import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from codex_proxy.client import CodingPlanClient
from codex_proxy.config import Config
from codex_proxy.converter import Converter
from codex_proxy.logging_utils import ConsoleFormatter, generate_request_id, should_use_color

logger = logging.getLogger(__name__)
console_logger = logging.getLogger("codex_proxy.console")


def _close_and_remove_handlers(logger_obj: logging.Logger) -> None:
    """Flush, close, and detach handlers from a logger."""
    for handler in list(logger_obj.handlers):
        try:
            handler.flush()
        except Exception:
            pass
        try:
            handler.close()
        except Exception:
            pass
        logger_obj.removeHandler(handler)


def configure_logging(
    config: Config,
    log_dir: Path | None = None,
    console_stream: TextIO | None = None,
) -> None:
    """Configure separate file and console logging sinks."""
    log_dir = log_dir or Path(__file__).parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    _close_and_remove_handlers(root_logger)
    root_logger.setLevel(logging.DEBUG)

    file_level = getattr(logging, config.logging.file_level.upper())
    file_handler = TimedRotatingFileHandler(
        log_dir / "codex-proxy.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(config.logging.format))
    root_logger.addHandler(file_handler)

    console_level = getattr(logging, config.logging.console_level.upper())
    console_logger = logging.getLogger("codex_proxy.console")
    _close_and_remove_handlers(console_logger)
    console_logger.setLevel(console_level)
    console_logger.propagate = False

    console_handler = logging.StreamHandler(console_stream)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(
        ConsoleFormatter(use_color=should_use_color(console_handler.stream))
    )
    console_logger.addHandler(console_handler)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = generate_request_id()
        request.state.started_at = time.perf_counter()
        request_id = request.state.request_id
        logger.info(
            "http.request.started request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        try:
            response = await call_next(request)
        except Exception:
            logger.info(
                "http.request.completed request_id=%s method=%s path=%s status=500",
                request_id,
                request.method,
                request.url.path,
            )
            raise

        logger.info(
            "http.request.completed request_id=%s method=%s path=%s status=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
        )
        return response


def create_app(config: Config) -> FastAPI:
    """Create FastAPI application.

    Args:
        config: Application configuration.

    Returns:
        Configured FastAPI application.
    """
    client = CodingPlanClient(config.coding_plan)
    converter = Converter()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        app.state.config = config
        app.state.client = client
        app.state.converter = converter
        yield
        # Shutdown
        await client.close()

    app = FastAPI(
        title="Codex Proxy",
        description="Adapts OpenAI Codex Responses API to Coding Plan Chat Completions API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Add validation error handler for debugging
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", generate_request_id())
        errors = exc.errors()
        body = (await request.body()).decode("utf-8", errors="replace")

        console_logger.error(
            "validation_failed status=422 error_count=%s",
            len(errors),
            extra={"request_id": request_id},
        )
        logger.error(
            "validation.errors request_id=%s errors=%s",
            request_id,
            json.dumps(errors, ensure_ascii=False, indent=2),
        )
        logger.error(
            "validation.body request_id=%s body=%s",
            request_id,
            body,
        )
        return JSONResponse(
            status_code=422,
            content={"detail": errors},
        )

    # Add logging middleware
    app.add_middleware(LoggingMiddleware)

    # Register routes
    from codex_proxy.router import register_routes
    register_routes(app, config, client, converter)

    return app


def run():
    """Run the application."""
    config = Config.load("config.yaml")
    configure_logging(config)
    app = create_app(config)

    console_logger.info(
        "listening on http://%s:%s default_model=%s",
        config.server.host,
        config.server.port,
        config.coding_plan.model,
    )
    logger.info(
        "server.starting host=%s port=%s default_model=%s base_url=%s",
        config.server.host,
        config.server.port,
        config.coding_plan.model,
        config.coding_plan.base_url,
    )

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        access_log=False,
        log_config=None,
    )


if __name__ == "__main__":
    run()
