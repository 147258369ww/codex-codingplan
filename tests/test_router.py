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