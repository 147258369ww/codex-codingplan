"""FastAPI application entry point."""

import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from codex_proxy.client import CodingPlanClient
from codex_proxy.config import Config
from codex_proxy.converter import Converter

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        logger.info(f">>> {request.method} {request.url.path}")
        response = await call_next(request)
        logger.info(f"<<< {request.method} {request.url.path} - {response.status_code}")
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
        import json
        logger.error("Validation error: %s", json.dumps(exc.errors(), ensure_ascii=False, indent=2))
        logger.error("Request body: %s", await request.body())
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
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

    # Create logs directory
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    # Configure logging with file handler
    log_level = getattr(logging, config.logging.level.upper())

    # Create formatters
    formatter = logging.Formatter(config.logging.format)

    # File handler - rotate daily, keep 7 days
    log_file = log_dir / "codex-proxy.log"
    file_handler = TimedRotatingFileHandler(
        log_file,
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logger.info("Logging initialized. Log file: %s", log_file)

    app = create_app(config)

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
    )


if __name__ == "__main__":
    run()