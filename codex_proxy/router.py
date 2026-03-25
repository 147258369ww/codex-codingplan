"""API route handlers."""

import json
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from codex_proxy.client import CodingPlanClient, CodingPlanAPIError
from codex_proxy.config import Config
from codex_proxy.converter import Converter
from codex_proxy.models import ResponsesRequest


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
    async def create_response(request: ResponsesRequest):
        """Handle Responses API request.

        Args:
            request: Responses API request body.

        Returns:
            Responses API response.
        """
        # Convert request
        chat_request = converter.to_chat_completions_request(
            request,
            config.coding_plan.model,
        )

        try:
            if request.stream:
                return StreamingResponse(
                    _stream_response(client, converter, chat_request, request.model),
                    media_type="text/event-stream",
                )
            else:
                # Non-streaming
                chat_response = await client.chat(chat_request)
                return converter.to_responses_response(chat_response)

        except CodingPlanAPIError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail={
                    "type": e.error_data.get("error", {}).get("type", "api_error"),
                    "message": e.error_data.get("error", {}).get("message", str(e)),
                },
            )


async def _stream_response(
    client: CodingPlanClient,
    converter: Converter,
    chat_request: dict[str, Any],
    model: str,
):
    """Generate streaming response.

    Args:
        client: Coding Plan client.
        converter: Format converter.
        chat_request: Chat Completions request.
        model: Model name.

    Yields:
        SSE formatted events.
    """
    response_id = None
    full_content = ""
    usage = {}

    stream = await client.chat(chat_request, stream=True)

    async for event in stream:
        if event.get("done"):
            # Send completed event
            completed = converter.create_completed_event(
                response_id or "resp_unknown",
                model,
                full_content,
                usage,
            )
            yield f"data: {json.dumps(completed)}\n\n"
            yield "data: [DONE]\n\n"
            break

        # Track response ID
        if not response_id and event.get("id"):
            chat_id = event["id"]
            if chat_id.startswith("chatcmpl-"):
                response_id = "resp_" + chat_id[9:]
            else:
                response_id = "resp_" + chat_id

        # Track usage if present
        if event.get("usage"):
            usage = event["usage"]

        # Convert event
        responses_event = converter.to_responses_stream_event(
            event,
            response_id or "resp_unknown",
            model,
        )

        if responses_event:
            # Track content for final event
            if responses_event.get("delta"):
                full_content += responses_event["delta"]

            yield f"data: {json.dumps(responses_event)}\n\n"