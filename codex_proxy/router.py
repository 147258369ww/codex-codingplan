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
from codex_proxy.tools import (
    ToolCallState,
    build_function_call_item,
    get_or_create_tool_call_state,
)

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
    content_index = 0
    created_sent = False
    text_item_added = False
    text_item_done = False
    tool_call_states: dict[int, ToolCallState] = {}

    def next_seq():
        nonlocal sequence_number
        sequence_number += 1
        return sequence_number

    def sse_event(payload: dict[str, Any]) -> str:
        payload["sequence_number"] = next_seq()
        return f"data: {json.dumps(payload)}\n\n"

    def emit_response_created() -> list[str]:
        nonlocal created_sent
        if created_sent:
            return []
        created_sent = True
        return [sse_event({
            "type": "response.created",
            "response": {
                "id": response_id,
                "object": "response",
                "created_at": time.time(),
                "status": "in_progress",
                "model": model,
            },
        })]

    def emit_text_item_added() -> list[str]:
        nonlocal text_item_added
        if text_item_added:
            return []
        text_item_added = True
        return emit_response_created() + [
            sse_event({
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "id": item_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [],
                },
            }),
            sse_event({
                "type": "response.content_part.added",
                "item_id": item_id,
                "output_index": 0,
                "content_index": content_index,
                "part": {"type": "output_text", "text": ""},
            }),
        ]

    def emit_tool_call_added(state: ToolCallState) -> list[str]:
        if state.added_sent:
            return []
        state.added_sent = True
        return emit_response_created() + [
            sse_event({
                "type": "response.output_item.added",
                "output_index": state.index,
                "item": build_function_call_item(state),
            })
        ]

    def emit_text_done() -> list[str]:
        nonlocal text_item_done
        if not text_item_added or text_item_done:
            return []
        text_item_done = True
        output_item = {
            "id": item_id,
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": full_content}],
        }
        return [
            sse_event({
                "type": "response.output_text.done",
                "item_id": item_id,
                "output_index": 0,
                "content_index": content_index,
                "text": full_content,
            }),
            sse_event({
                "type": "response.content_part.done",
                "item_id": item_id,
                "output_index": 0,
                "content_index": content_index,
                "part": {
                    "type": "output_text",
                    "text": full_content,
                },
            }),
            sse_event({
                "type": "response.output_item.done",
                "output_index": 0,
                "item": output_item,
            }),
        ]

    def emit_tool_call_done(state: ToolCallState) -> list[str]:
        if not state.added_sent or state.done_sent:
            return []
        state.done_sent = True
        return [
            sse_event({
                "type": "response.function_call_arguments.done",
                "item_id": state.item_id,
                "output_index": state.index,
                "arguments": state.arguments,
            }),
            sse_event({
                "type": "response.output_item.done",
                "output_index": state.index,
                "item": build_function_call_item(state),
            }),
        ]

    def emit_open_items_done() -> list[str]:
        events = emit_text_done()
        for index in sorted(tool_call_states):
            events.extend(emit_tool_call_done(tool_call_states[index]))
        return events

    def build_completed_output_items() -> list[dict[str, Any]]:
        output_items: list[dict[str, Any]] = []
        if text_item_added:
            output_items.append({
                "id": item_id,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": full_content}],
            })
        for index in sorted(tool_call_states):
            state = tool_call_states[index]
            if state.added_sent:
                output_items.append(build_function_call_item(state))
        return output_items

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
                for payload in emit_open_items_done():
                    yield payload

                # 4. response.completed
                logger.info("Stream done, sending completed event")
                completed = converter.create_completed_event(
                    response_id,
                    model,
                    full_content,
                    usage,
                    output_items=build_completed_output_items(),
                )
                yield f"data: {json.dumps(completed)}\n\n"
                yield "data: [DONE]\n\n"
                break

            choices = event.get("choices") or []
            choice = choices[0] if choices else {}
            delta = choice.get("delta", {}) or {}
            finish_reason = choice.get("finish_reason")

            tool_calls = delta.get("tool_calls") or []
            for tool_call in tool_calls:
                state = get_or_create_tool_call_state(tool_call_states, tool_call)
                for payload in emit_tool_call_added(state):
                    yield payload

                tool_event = converter.to_responses_stream_event(
                    {"choices": [{"delta": {"tool_calls": [tool_call]}, "finish_reason": None}]},
                    response_id,
                    model,
                )
                if tool_event and tool_event.get("delta"):
                    state.arguments += tool_event["delta"]
                    tool_event["item_id"] = state.item_id
                    tool_event["output_index"] = state.index
                    yield sse_event(tool_event)

            text_delta = {
                key: value
                for key, value in delta.items()
                if key != "tool_calls"
            }
            if text_delta:
                responses_event = converter.to_responses_stream_event(
                    {"choices": [{"delta": text_delta, "finish_reason": None}]},
                    response_id,
                    model,
                )
                if responses_event and responses_event.get("delta"):
                    for payload in emit_text_item_added():
                        yield payload
                    responses_event["item_id"] = item_id
                    responses_event["content_index"] = content_index
                    full_content += responses_event["delta"]
                    yield sse_event(responses_event)
                else:
                    logger.debug("Event returned None (filtered out)")

            if finish_reason:
                for payload in emit_open_items_done():
                    yield payload

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
