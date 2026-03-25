"""API route handlers."""

import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from codex_proxy.client import CodingPlanClient, CodingPlanAPIError
from codex_proxy.config import Config
from codex_proxy.converter import Converter
from codex_proxy.models import ResponsesRequest

logger = logging.getLogger(__name__)


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
        logger.info("=== Incoming request ===")
        logger.info(f"Model: {request.model}")
        logger.info(f"Stream: {request.stream}")
        logger.info(f"Input type: {type(request.input).__name__}")

        # Resolve model name (e.g., gpt-5.4 -> qwen3.5-plus)
        actual_model = config.coding_plan.resolve_model(request.model)
        logger.info(f"Resolved model: {actual_model}")

        # Convert request
        chat_request = converter.to_chat_completions_request(
            request,
            actual_model,
        )
        logger.info("Converted request: %s", json.dumps(chat_request, ensure_ascii=False, indent=2))

        try:
            if request.stream:
                return StreamingResponse(
                    _stream_response(client, converter, chat_request, actual_model),
                    media_type="text/event-stream",
                )
            else:
                # Non-streaming
                chat_response = await client.chat(chat_request)
                return converter.to_responses_response(chat_response)

        except CodingPlanAPIError as e:
            # Defensive null checks with safe defaults
            error_data = e.error_data or {}
            error_obj = error_data.get("error") or {}
            error_type = error_obj.get("type") if isinstance(error_obj, dict) else "api_error"
            error_message = error_obj.get("message") if isinstance(error_obj, dict) else str(e)

            raise HTTPException(
                status_code=e.status_code,
                detail={
                    "type": error_type or "api_error",
                    "message": error_message or "An API error occurred",
                },
            )
        except Exception as e:
            # Catch-all for unexpected errors
            raise HTTPException(
                status_code=500,
                detail={
                    "type": "internal_error",
                    "message": f"An unexpected error occurred: {str(e)}",
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
    import time
    import uuid

    response_id = "resp_" + str(uuid.uuid4())[:8]
    item_id = "msg_" + str(uuid.uuid4())[:8]
    full_content = ""
    usage = {}
    sequence_number = 0
    output_index = 0
    content_index = 0
    initialized = False

    def next_seq():
        nonlocal sequence_number
        sequence_number += 1
        return sequence_number

    try:
        stream = await client.chat(chat_request, stream=True)
        logger.info("Stream started, waiting for events...")

        async for event in stream:
            logger.debug("Processing event: %s", json.dumps(event, ensure_ascii=False)[:300])

            # Track response ID from upstream
            if event.get("id"):
                chat_id = event["id"]
                if chat_id.startswith("chatcmpl-"):
                    response_id = "resp_" + chat_id[9:]

            # Track usage if present
            if event.get("usage"):
                usage = event["usage"]

            if event.get("done"):
                # Send completion events in correct order
                # 1. response.output_text.done
                text_done_event = {
                    "type": "response.output_text.done",
                    "item_id": item_id,
                    "output_index": output_index,
                    "content_index": content_index,
                    "text": full_content,
                    "sequence_number": next_seq(),
                }
                yield f"data: {json.dumps(text_done_event)}\n\n"

                # 2. response.content_part.done
                content_part_done = {
                    "type": "response.content_part.done",
                    "item_id": item_id,
                    "output_index": output_index,
                    "content_index": content_index,
                    "part": {
                        "type": "output_text",
                        "text": full_content,
                    },
                    "sequence_number": next_seq(),
                }
                yield f"data: {json.dumps(content_part_done)}\n\n"

                # 3. response.output_item.done
                output_item = {
                    "id": item_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": full_content}],
                }
                output_item_done = {
                    "type": "response.output_item.done",
                    "output_index": output_index,
                    "item": output_item,
                    "sequence_number": next_seq(),
                }
                yield f"data: {json.dumps(output_item_done)}\n\n"

                # 4. response.completed
                logger.info("Stream done, sending completed event")
                completed = converter.create_completed_event(
                    response_id,
                    model,
                    full_content,
                    usage,
                )
                yield f"data: {json.dumps(completed)}\n\n"
                yield "data: [DONE]\n\n"
                break

            # Send initialization events on first content
            if not initialized:
                # 1. response.created
                created_event = {
                    "type": "response.created",
                    "response": {
                        "id": response_id,
                        "object": "response",
                        "created_at": time.time(),
                        "status": "in_progress",
                        "model": model,
                    },
                    "sequence_number": next_seq(),
                }
                yield f"data: {json.dumps(created_event)}\n\n"

                # 2. response.output_item.added
                output_item_added = {
                    "type": "response.output_item.added",
                    "output_index": output_index,
                    "item": {
                        "id": item_id,
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                    },
                    "sequence_number": next_seq(),
                }
                yield f"data: {json.dumps(output_item_added)}\n\n"

                # 3. response.content_part.added
                content_part_added = {
                    "type": "response.content_part.added",
                    "item_id": item_id,
                    "output_index": output_index,
                    "content_index": content_index,
                    "part": {"type": "output_text", "text": ""},
                    "sequence_number": next_seq(),
                }
                yield f"data: {json.dumps(content_part_added)}\n\n"

                initialized = True

            # Convert event
            responses_event = converter.to_responses_stream_event(
                event,
                response_id,
                model,
            )

            if responses_event:
                # Add required fields to the event
                responses_event["item_id"] = item_id
                responses_event["content_index"] = content_index
                responses_event["sequence_number"] = next_seq()

                logger.debug("Converted event: %s", json.dumps(responses_event, ensure_ascii=False)[:200])
                # Track content for final event
                if responses_event.get("delta"):
                    full_content += responses_event["delta"]

                yield f"data: {json.dumps(responses_event)}\n\n"
            else:
                logger.debug("Event returned None (filtered out)")

    except CodingPlanAPIError as e:
        # Yield error event for API errors during streaming
        error_data = e.error_data or {}
        error_obj = error_data.get("error") or {}
        error_type = error_obj.get("type") if isinstance(error_obj, dict) else "api_error"
        error_message = error_obj.get("message") if isinstance(error_obj, dict) else str(e)

        error_event = {
            "type": "error",
            "error": {
                "type": error_type or "api_error",
                "message": error_message or "An API error occurred",
            },
        }
        yield f"data: {json.dumps(error_event)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        # Yield error event for unexpected errors during streaming
        error_event = {
            "type": "error",
            "error": {
                "type": "internal_error",
                "message": f"An unexpected error occurred: {str(e)}",
            },
        }
        yield f"data: {json.dumps(error_event)}\n\n"
        yield "data: [DONE]\n\n"