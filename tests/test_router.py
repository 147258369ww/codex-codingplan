import io
import json
import logging
import re

import pytest
import respx
from httpx import Response
from fastapi.testclient import TestClient

from codex_proxy.main import configure_logging, create_app
from codex_proxy.config import Config, ServerConfig, CodingPlanConfig, LoggingConfig


@pytest.fixture
def test_config():
    return Config(
        server=ServerConfig(host="127.0.0.1", port=8080),
        coding_plan=CodingPlanConfig(
            base_url="https://api.test.com/v1",
            api_key="test-key",
            model="test-model",
            timeout=30,
        ),
        logging=LoggingConfig(),
    )


@pytest.fixture
def client(test_config):
    app = create_app(test_config)
    return TestClient(app)


@pytest.fixture(autouse=True)
def restore_logging_state():
    root_logger = logging.getLogger()
    console_logger = logging.getLogger("codex_proxy.console")

    original_state = {
        root_logger: {
            "level": root_logger.level,
            "propagate": root_logger.propagate,
            "disabled": root_logger.disabled,
            "handlers": list(root_logger.handlers),
        },
        console_logger: {
            "level": console_logger.level,
            "propagate": console_logger.propagate,
            "disabled": console_logger.disabled,
            "handlers": list(console_logger.handlers),
        },
    }

    yield

    for logger_obj, state in original_state.items():
        current_handlers = list(logger_obj.handlers)
        for handler in current_handlers:
            logger_obj.removeHandler(handler)
            if handler not in state["handlers"]:
                try:
                    handler.flush()
                except Exception:
                    pass
                try:
                    handler.close()
                except Exception:
                    pass

        logger_obj.setLevel(state["level"])
        logger_obj.propagate = state["propagate"]
        logger_obj.disabled = state["disabled"]

        for handler in state["handlers"]:
            logger_obj.addHandler(handler)


def _create_logged_client(test_config, tmp_path):
    console_stream = io.StringIO()
    configure_logging(test_config, log_dir=tmp_path, console_stream=console_stream)
    app = create_app(test_config)
    return TestClient(app), console_stream, tmp_path / "codex-proxy.log"


def _extract_request_id(output: str) -> str:
    match = re.search(r"req_[0-9a-f]{4}", output)
    assert match is not None
    return match.group(0)


class TestRouter:
    def test_health_check(self, client):
        """Test health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    @respx.mock
    def test_responses_endpoint_non_streaming(self, client):
        """Test /v1/responses endpoint."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "model": "test-model",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "Hello!"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                },
            )
        )

        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt-5",
                "input": "Hi",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["object"] == "response"
        assert data["status"] == "completed"
        assert data["output_text"] == "Hello!"

    def test_responses_validation_error(self, client):
        """Test validation error response."""
        response = client.post(
            "/v1/responses",
            json={},  # Missing required fields
        )

        assert response.status_code == 422

    @respx.mock
    def test_responses_with_instructions(self, client):
        """Test that instructions become system message."""
        route = respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(200, json={"id": "test", "choices": [], "usage": {}})
        )

        client.post(
            "/v1/responses",
            json={
                "model": "gpt-5",
                "input": "Hi",
                "instructions": "Be helpful",
            },
        )

        request_body = route.calls.last.request.read()
        data = json.loads(request_body)
        assert data["messages"][0]["role"] == "system"
        assert data["messages"][0]["content"] == "Be helpful"

    @respx.mock
    def test_responses_endpoint_streaming(self, client):
        """Test /v1/responses streaming endpoint."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                content=(
                    b'data: {"id": "chatcmpl-test", "choices": [{"delta": {"content": "He"}}]}\n\n'
                    b'data: {"choices": [{"delta": {"content": "llo"}}]}\n\n'
                    b'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n'
                    b'data: [DONE]\n\n'
                ),
                headers={"content-type": "text/event-stream"},
            )
        )

        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt-5",
                "input": "Hi",
                "stream": True,
            },
        )

        assert response.status_code == 200
        # Read the streaming response
        content = response.content.decode()
        assert "response.output_text.delta" in content
        assert "response.completed" in content

    @respx.mock
    def test_streaming_tool_call_events(self, client):
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                content=(
                    b'data: {"id":"chatcmpl-test","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_123","type":"function","function":{"name":"get_weather","arguments":"{\\"city\\":"}}]}}]}\n\n'
                    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"Hangzhou\\"}"}}]}}]}\n\n'
                    b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                    b'data: [DONE]\n\n'
                ),
                headers={"content-type": "text/event-stream"},
            )
        )

        response = client.post(
            "/v1/responses",
            json={"model": "gpt-5", "input": "Weather?", "stream": True},
        )
        content = response.content.decode()

        assert "response.function_call_arguments.delta" in content
        assert "response.function_call_arguments.done" in content
        assert "response.output_item.done" in content

    @respx.mock
    def test_streaming_mixed_text_and_tool_items_preserve_output_order(self, client):
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                content=(
                    b'data: {"id":"chatcmpl-test","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_123","type":"function","function":{"name":"get_weather","arguments":"{\\"city\\":"}}]}}]}\n\n'
                    b'data: {"choices":[{"delta":{"content":"Let me check."}}]}\n\n'
                    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"Hangzhou\\"}"}}]}}]}\n\n'
                    b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                    b'data: [DONE]\n\n'
                ),
                headers={"content-type": "text/event-stream"},
            )
        )

        response = client.post(
            "/v1/responses",
            json={"model": "gpt-5", "input": "Weather?", "stream": True},
        )

        assert response.status_code == 200
        events = []
        for line in response.content.decode().splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                continue
            events.append(json.loads(payload))

        added_events = [
            event for event in events
            if event["type"] == "response.output_item.added"
        ]
        assert [event["item"]["type"] for event in added_events] == [
            "function_call",
            "message",
        ]
        assert [event["output_index"] for event in added_events] == [0, 1]

        tool_delta = next(
            event for event in events
            if event["type"] == "response.function_call_arguments.delta"
        )
        text_delta = next(
            event for event in events
            if event["type"] == "response.output_text.delta"
        )
        assert tool_delta["output_index"] == 0
        assert text_delta["output_index"] == 1

        completed = next(
            event for event in events
            if event["type"] == "response.completed"
        )
        assert [
            item["type"] for item in completed["response"]["output"]
        ] == ["function_call", "message"]
        assert completed["response"]["output"][0]["call_id"] == "call_123"
        assert completed["response"]["output"][1]["content"][0]["text"] == "Let me check."

    @respx.mock
    def test_api_error_unauthorized(self, client):
        """Test API error (401 Unauthorized) is properly returned."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                401,
                json={
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Invalid API key",
                    }
                },
            )
        )

        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt-5",
                "input": "Hi",
            },
        )

        assert response.status_code == 401
        data = response.json()
        assert data["detail"]["type"] == "invalid_request_error"
        assert data["detail"]["message"] == "Invalid API key"

    @respx.mock
    def test_api_error_with_null_error_data(self, client):
        """Test API error handles null/missing error data gracefully."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                500,
                json={},
            )
        )

        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt-5",
                "input": "Hi",
            },
        )

        assert response.status_code == 500
        data = response.json()
        assert data["detail"]["type"] == "api_error"
        assert "message" in data["detail"]

    @respx.mock
    def test_streaming_api_error(self, client):
        """Test streaming error handling yields error event."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                401,
                content=b'{"error": {"type": "invalid_request_error", "message": "Invalid API key"}}',
                headers={"content-type": "text/event-stream"},
            )
        )

        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt-5",
                "input": "Hi",
                "stream": True,
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert '"type": "error"' in content
        assert "invalid_request_error" in content
        assert "Invalid API key" in content
        assert "[DONE]" in content

    @respx.mock
    def test_streaming_with_null_error_data(self, client):
        """Test streaming handles null/missing error data gracefully."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                500,
                content=b'{}',
                headers={"content-type": "text/event-stream"},
            )
        )

        response = client.post(
            "/v1/responses",
            json={
                "model": "gpt-5",
                "input": "Hi",
                "stream": True,
            },
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert '"type": "error"' in content
        assert "api_error" in content
        assert "[DONE]" in content

    @respx.mock
    def test_non_streaming_request_logs_request_scope(self, test_config, tmp_path):
        test_config.coding_plan.model_mapping = {"gpt-5": "resolved-model"}
        test_config.logging.payload_max_chars = 80
        logged_client, console_stream, file_path = _create_logged_client(test_config, tmp_path)

        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "model": "resolved-model",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "Hello from upstream"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                },
            )
        )

        response = logged_client.post(
            "/v1/responses",
            json={
                "model": "gpt-5",
                "input": "x" * 200,
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "lookup_weather",
                            "parameters": {"type": "object"},
                        },
                    }
                ],
            },
        )

        assert response.status_code == 200

        console_output = console_stream.getvalue()
        request_id = _extract_request_id(console_output)
        file_output = file_path.read_text(encoding="utf-8")

        assert f"{request_id}  start POST /v1/responses model=gpt-5->resolved-model stream=False input=1 item tool_count=1" in console_output
        assert f"{request_id}  done status=200" in console_output
        assert "text_size=19B" in console_output
        assert "finish_reason=stop" in console_output
        assert "request.started" in file_output
        assert "request.payload" in file_output
        assert "upstream.request" in file_output
        assert request_id in file_output
        assert "...<truncated>" in file_output

    @respx.mock
    def test_streaming_request_logs_tool_call_and_done(self, test_config, tmp_path):
        logged_client, console_stream, _ = _create_logged_client(test_config, tmp_path)

        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                content=(
                    b'data: {"id":"chatcmpl-test","choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_123","type":"function","function":{"name":"get_weather","arguments":"{\\"city\\":"}}]}}]}\n\n'
                    b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"Hangzhou\\"}"}}]}}]}\n\n'
                    b'data: {"choices":[{"delta":{"content":"Done"}}]}\n\n'
                    b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                    b'data: [DONE]\n\n'
                ),
                headers={"content-type": "text/event-stream"},
            )
        )

        response = logged_client.post(
            "/v1/responses",
            json={"model": "gpt-5", "input": "Weather?", "stream": True},
        )

        assert response.status_code == 200

        console_output = console_stream.getvalue()
        request_id = _extract_request_id(console_output)

        assert f"{request_id}  tool_call name=get_weather call_id=call_123" in console_output
        assert "args_size=" in console_output
        assert f"{request_id}  done status=200" in console_output
        assert "finish_reason=stream_done" in console_output
        assert "text_size=4B" in console_output

    @respx.mock
    def test_api_error_logs_upstream_error_summary(self, test_config, tmp_path):
        logged_client, console_stream, file_path = _create_logged_client(test_config, tmp_path)

        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                401,
                json={
                    "error": {
                        "type": "invalid_request_error",
                        "message": "Invalid API key",
                    }
                },
            )
        )

        response = logged_client.post(
            "/v1/responses",
            json={"model": "gpt-5", "input": "Hi"},
        )

        assert response.status_code == 401

        console_output = console_stream.getvalue()
        request_id = _extract_request_id(console_output)
        file_output = file_path.read_text(encoding="utf-8")

        assert f"{request_id}  upstream_error status=401 error_type=invalid_request_error message=Invalid API key" in console_output
        assert "upstream.request.error" in file_output
        assert request_id in file_output
