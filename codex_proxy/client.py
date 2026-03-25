"""HTTP client for Coding Plan API."""

import json
from typing import Any, AsyncGenerator

import httpx

from codex_proxy.config import CodingPlanConfig


class CodingPlanAPIError(Exception):
    """Error from Coding Plan API."""

    def __init__(self, status_code: int, error_data: dict):
        self.status_code = status_code
        self.error_data = error_data
        super().__init__(error_data.get("error", {}).get("message", "API Error"))


class CodingPlanClient:
    """Async HTTP client for Coding Plan API."""

    def __init__(self, config: CodingPlanConfig):
        self.base_url = config.base_url.rstrip("/")
        self.api_key = config.api_key
        self.timeout = config.timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def chat(
        self,
        request: dict[str, Any],
        stream: bool = False,
    ) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
        """Send chat request to Coding Plan.

        Args:
            request: Chat Completions request dict.
            stream: Whether to stream the response.

        Returns:
            Response dict for non-streaming, or async generator for streaming.

        Raises:
            CodingPlanAPIError: If the API returns an error.
        """
        client = await self._get_client()

        if stream:
            return self._request_stream(client, request)

        response = await client.post(
            f"{self.base_url}/chat/completions",
            json=request,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        if response.status_code >= 400:
            error_data = response.json()
            raise CodingPlanAPIError(response.status_code, error_data)

        return response.json()

    async def _request_stream(
        self,
        client: httpx.AsyncClient,
        request: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream chat response.

        Args:
            client: HTTP client.
            request: Chat Completions request dict.

        Yields:
            Parsed SSE events as dicts.
        """
        async with client.stream(
            "POST",
            f"{self.base_url}/chat/completions",
            json=request,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        ) as response:
            if response.status_code >= 400:
                error_data = await response.aread()
                raise CodingPlanAPIError(
                    response.status_code,
                    json.loads(error_data),
                )

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue

                data = line[6:]  # Remove "data: " prefix

                if data == "[DONE]":
                    yield {"done": True}
                    break

                try:
                    event = json.loads(data)
                    yield event
                except json.JSONDecodeError:
                    continue