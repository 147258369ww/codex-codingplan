"""API route handlers."""

import json
import logging
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from codex_proxy.client import CodingPlanClient, CodingPlanAPIError
from codex_proxy.config import Config
from codex_proxy.converter import Converter
from codex_proxy.logging_utils import format_bytes, format_duration, truncate_text
from codex_proxy.models import ResponsesRequest
from codex_proxy.tools import (
    ToolCallState,
    build_function_call_item,
    get_or_create_tool_call_state,
)

logger = logging.getLogger(__name__)
console_logger = logging.getLogger("codex_proxy.console")


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _get_started_at(request: Request) -> float:
    return getattr(request.state, "started_at", time.perf_counter())


def _summarize_input_count(input_value: str | list[Any]) -> str:
    count = 1 if isinstance(input_value, str) else len(input_value)
    label = "item" if count == 1 else "items"
    return f"{count} {label}"


def _serialize_payload(payload: dict[str, Any], limit: int) -> tuple[str, bool]:
    return truncate_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        limit,
    )


def _extract_message_text(chat_response: dict[str, Any]) -> str:
    choices = chat_response.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content") or ""


def _extract_finish_reason(chat_response: dict[str, Any]) -> str:
    choices = chat_response.get("choices") or []
    if not choices:
        return "unknown"
    return choices[0].get("finish_reason") or "unknown"


def _extract_tool_count_from_response(chat_response: dict[str, Any]) -> int:
    choices = chat_response.get("choices") or []
    if not choices:
        return 0
    message = choices[0].get("message") or {}
    return len(message.get("tool_calls") or [])


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
    async def create_response(http_request: Request, request: ResponsesRequest):
        """Handle Responses API request.

        Args:
            request: Responses API request body.

        Returns:
            Responses API response.
        """
        request_id = _get_request_id(http_request)
        started_at = _get_started_at(http_request)
        payload_max_chars = config.logging.payload_max_chars

        # Resolve model name (e.g., gpt-5.4 -> qwen3.5-plus)
        actual_model = config.coding_plan.resolve_model(request.model)
        input_summary = _summarize_input_count(request.input)
        tool_count = len(request.tools or [])

        if not request.stream:
            console_logger.info(
                "start POST /v1/responses model=%s->%s stream=%s input=%s tool_count=%s",
                request.model,
                actual_model,
                request.stream,
                input_summary,
                tool_count,
                extra={"request_id": request_id},
            )
        logger.info(
            "request.started request_id=%s method=POST path=/v1/responses model=%s resolved_model=%s stream=%s input=%s tool_count=%s",
            request_id,
            request.model,
            actual_model,
            request.stream,
            input_summary,
            tool_count,
        )

        # Convert request
        chat_request = converter.to_chat_completions_request(
            request,
            actual_model,
        )
        serialized_payload, payload_truncated = _serialize_payload(chat_request, payload_max_chars)
        logger.info(
            "request.payload request_id=%s truncated=%s payload=%s",
            request_id,
            payload_truncated,
            serialized_payload,
        )

        try:
            if request.stream:
                return StreamingResponse(
                    _stream_response(
                        client,
                        converter,
                        chat_request,
                        actual_model,
                        request_id=request_id,
                        started_at=started_at,
                        payload_max_chars=payload_max_chars,
                    ),
                    media_type="text/event-stream",
                )
            else:
                # Non-streaming
                chat_response = await client.chat(
                    chat_request,
                    request_id=request_id,
                    payload_max_chars=payload_max_chars,
                )
                response_body = converter.to_responses_response(chat_response)
                latency = time.perf_counter() - started_at
                text = _extract_message_text(chat_response)
                response_tool_count = _extract_tool_count_from_response(chat_response)
                finish_reason = _extract_finish_reason(chat_response)
                text_size = format_bytes(len(text.encode("utf-8")))

                console_logger.info(
                    "done status=200 latency=%s text_size=%s tool_count=%s finish_reason=%s",
                    format_duration(latency),
                    text_size,
                    response_tool_count,
                    finish_reason,
                    extra={"request_id": request_id},
                )
                logger.info(
                    "request.completed request_id=%s status=200 latency=%s text_size=%s tool_count=%s finish_reason=%s",
                    request_id,
                    format_duration(latency),
                    text_size,
                    response_tool_count,
                    finish_reason,
                )
                return response_body

        except CodingPlanAPIError as e:
            # Defensive null checks with safe defaults
            error_data = e.error_data or {}
            error_obj = error_data.get("error") or {}
            error_type = error_obj.get("type") if isinstance(error_obj, dict) else "api_error"
            error_message = error_obj.get("message") if isinstance(error_obj, dict) else str(e)

            console_logger.error(
                "upstream_error status=%s error_type=%s message=%s",
                e.status_code,
                error_type or "api_error",
                error_message or "An API error occurred",
                extra={"request_id": request_id},
            )
            logger.error(
                "request.failed request_id=%s status=%s error_type=%s message=%s error=%s",
                request_id,
                e.status_code,
                error_type or "api_error",
                error_message or "An API error occurred",
                json.dumps(error_data, ensure_ascii=False, indent=2),
            )

            raise HTTPException(
                status_code=e.status_code,
                detail={
                    "type": error_type or "api_error",
                    "message": error_message or "An API error occurred",
                },
            )
        except Exception as e:
            # Catch-all for unexpected errors
            console_logger.error(
                "internal_error status=500 message=%s",
                str(e),
                extra={"request_id": request_id},
            )
            logger.exception("request.internal_error request_id=%s", request_id)
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
    request_id: str,
    started_at: float,
    payload_max_chars: int,
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
    import uuid

    response_id = "resp_" + str(uuid.uuid4())[:8]
    item_id = "msg_" + str(uuid.uuid4())[:8]
    full_content = ""
    usage = {}
    sequence_number = 0
    next_output_index = 0
    content_index = 0
    created_sent = False
    text_item_added = False
    text_item_done = False
    text_output_index: int | None = None
    tool_call_states: dict[int, ToolCallState] = {}

    def next_seq():
        nonlocal sequence_number
        sequence_number += 1
        return sequence_number

    def allocate_output_index() -> int:
        nonlocal next_output_index
        output_index = next_output_index
        next_output_index += 1
        return output_index

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
        nonlocal text_item_added, text_output_index
        if text_item_added:
            return []
        text_item_added = True
        text_output_index = allocate_output_index()
        return emit_response_created() + [
            sse_event({
                "type": "response.output_item.added",
                "output_index": text_output_index,
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
                "output_index": text_output_index,
                "content_index": content_index,
                "part": {"type": "output_text", "text": ""},
            }),
        ]

    def emit_tool_call_added(state: ToolCallState) -> list[str]:
        if state.added_sent:
            return []
        state.added_sent = True
        state.output_index = allocate_output_index()
        return emit_response_created() + [
            sse_event({
                "type": "response.output_item.added",
                "output_index": state.output_index,
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
                "output_index": text_output_index,
                "content_index": content_index,
                "text": full_content,
            }),
            sse_event({
                "type": "response.content_part.done",
                "item_id": item_id,
                "output_index": text_output_index,
                "content_index": content_index,
                "part": {
                    "type": "output_text",
                    "text": full_content,
                },
            }),
            sse_event({
                "type": "response.output_item.done",
                "output_index": text_output_index,
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
                "output_index": state.output_index,
                "arguments": state.arguments,
            }),
            sse_event({
                "type": "response.output_item.done",
                "output_index": state.output_index,
                "item": build_function_call_item(state),
            }),
        ]

    def emit_open_items_done() -> list[str]:
        events = emit_text_done()
        for index in sorted(tool_call_states):
            events.extend(emit_tool_call_done(tool_call_states[index]))
        return events

    def build_completed_output_items() -> list[dict[str, Any]]:
        ordered_items: list[tuple[int, dict[str, Any]]] = []
        if text_item_added:
            ordered_items.append((text_output_index, {
                "id": item_id,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": full_content}],
            }))
        for state in tool_call_states.values():
            if state.added_sent:
                ordered_items.append((state.output_index, build_function_call_item(state)))
        ordered_items.sort(key=lambda item: item[0])
        return [item for _, item in ordered_items]

    try:
        stream = await client.chat(
            chat_request,
            stream=True,
            request_id=request_id,
            payload_max_chars=payload_max_chars,
        )
        logger.info("stream.started request_id=%s model=%s", request_id, model)

        async for event in stream:
            logger.debug(
                "stream.event request_id=%s event=%s",
                request_id,
                json.dumps(event, ensure_ascii=False)[:300],
            )

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

                latency = time.perf_counter() - started_at
                text_size = format_bytes(len(full_content.encode("utf-8")))
                logger.info(
                    "stream.completed request_id=%s status=200 latency=%s text_size=%s tool_count=%s finish_reason=stream_done",
                    request_id,
                    format_duration(latency),
                    text_size,
                    len(tool_call_states),
                )
                console_logger.info(
                    "done status=200 latency=%s text_size=%s tool_count=%s finish_reason=stream_done",
                    format_duration(latency),
                    text_size,
                    len(tool_call_states),
                    extra={"request_id": request_id},
                )
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
                first_observation = not state.added_sent
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
                    tool_event["output_index"] = state.output_index
                    yield sse_event(tool_event)
                if first_observation:
                    console_logger.info(
                        "tool_call name=%s call_id=%s args_size=%s",
                        state.name or "unknown",
                        state.call_id,
                        format_bytes(len(state.arguments.encode("utf-8"))),
                        extra={"request_id": request_id},
                    )

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
                    responses_event["output_index"] = text_output_index
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
        console_logger.error(
            "upstream_error status=%s error_type=%s message=%s",
            e.status_code,
            error_type or "api_error",
            error_message or "An API error occurred",
            extra={"request_id": request_id},
        )
        logger.error(
            "stream.upstream_error request_id=%s status=%s error_type=%s message=%s error=%s",
            request_id,
            e.status_code,
            error_type or "api_error",
            error_message or "An API error occurred",
            json.dumps(error_data, ensure_ascii=False, indent=2),
        )

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
        console_logger.error(
            "internal_error status=500 message=%s",
            str(e),
            extra={"request_id": request_id},
        )
        logger.exception("stream.internal_error request_id=%s", request_id)
        error_event = {
            "type": "error",
            "error": {
                "type": "internal_error",
                "message": f"An unexpected error occurred: {str(e)}",
            },
        }
        yield f"data: {json.dumps(error_event)}\n\n"
        yield "data: [DONE]\n\n"
