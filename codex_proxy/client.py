"""HTTP client for Coding Plan API."""

import json
import logging
from typing import Any, AsyncGenerator

import httpx

from codex_proxy.config import CodingPlanConfig
from codex_proxy.logging_utils import truncate_text

logger = logging.getLogger(__name__)


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

    async def __aenter__(self) -> "CodingPlanClient":
        """Enter async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context manager and close client."""
        await self.close()

    async def chat(
        self,
        request: dict[str, Any],
        stream: bool = False,
        request_id: str | None = None,
        payload_max_chars: int = 4000,
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
        request_payload, was_truncated = truncate_text(
            json.dumps(request, ensure_ascii=False, indent=2),
            payload_max_chars,
        )

        logger.debug(
            "upstream.request request_id=%s stream=%s truncated=%s payload=%s",
            request_id,
            stream,
            was_truncated,
            request_payload,
        )

        if stream:
            return self._request_stream(
                client,
                request,
                request_id=request_id,
                request_payload=request_payload,
                payload_truncated=was_truncated,
            )

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
            logger.error(
                "upstream.request.error request_id=%s status=%s truncated=%s payload=%s error=%s",
                request_id,
                response.status_code,
                was_truncated,
                request_payload,
                json.dumps(error_data, ensure_ascii=False, indent=2),
            )
            raise CodingPlanAPIError(response.status_code, error_data)

        return response.json()

    async def _request_stream(
        self,
        client: httpx.AsyncClient,
        request: dict[str, Any],
        request_id: str | None,
        request_payload: str,
        payload_truncated: bool,
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
                try:
                    parsed_error = json.loads(error_data)
                except json.JSONDecodeError:
                    parsed_error = {"error": {"message": error_data.decode("utf-8", errors="replace")}}
                logger.error(
                    "upstream.request.error request_id=%s status=%s stream=True truncated=%s payload=%s error=%s",
                    request_id,
                    response.status_code,
                    payload_truncated,
                    request_payload,
                    json.dumps(parsed_error, ensure_ascii=False, indent=2),
                )
                raise CodingPlanAPIError(
                    response.status_code,
                    parsed_error,
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
                    logger.debug("Received SSE event: %s", json.dumps(event, ensure_ascii=False)[:200])
                    yield event
                except json.JSONDecodeError:
                    logger.debug("Malformed JSON in SSE event: %s", data)
                    continue
