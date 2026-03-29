import json

import pytest
import respx
from httpx import Response
from fastapi.testclient import TestClient

from codex_proxy.main import create_app
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
