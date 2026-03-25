"""FastAPI application entry point."""

import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI

from codex_proxy.client import CodingPlanClient
from codex_proxy.config import Config
from codex_proxy.converter import Converter


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

    # Register routes
    from codex_proxy.router import register_routes
    register_routes(app, config, client, converter)

    return app


def run():
    """Run the application."""
    config = Config.load("config.yaml")
    app = create_app(config)

    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
    )


if __name__ == "__main__":
    run()