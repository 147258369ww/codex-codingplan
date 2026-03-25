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

    This is a stub implementation. The config, client, and converter parameters
    will be used by route handlers in the full implementation (Task 3) to:
    - Access configuration for request processing
    - Make API calls to the Coding Plan service via client
    - Convert between OpenAI and Coding Plan formats via converter

    Args:
        app: FastAPI application.
        config: Configuration (unused in stub, reserved for full implementation).
        client: Coding Plan client (unused in stub, reserved for full implementation).
        converter: Format converter (unused in stub, reserved for full implementation).
    """
    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "ok"}

    @app.post("/v1/responses")
    async def create_response():
        """Responses API endpoint (stub)."""
        return {"message": "Not implemented yet"}