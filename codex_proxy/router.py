"""API route handlers."""

from fastapi import FastAPI

from codex_proxy.client import CodingPlanClient
from codex_proxy.config import Config
from codex_proxy.converter import Converter


def register_routes(
    app: FastAPI,
    config: Config,
    client: CodingPlanClient,
    converter: Converter,
):
    """Register API routes.

    Args:
        app: FastAPI application.
        config: Configuration.
        client: Coding Plan client.
        converter: Format converter.
    """
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "ok"}

    @app.post("/v1/responses")
    async def create_response():
        """Responses API endpoint (stub)."""
        return {"message": "Not implemented yet"}