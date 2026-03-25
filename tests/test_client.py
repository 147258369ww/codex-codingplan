# codex-proxy/tests/test_client.py
"""Tests for HTTP client module."""

import pytest
import respx
from httpx import Response

from codex_proxy.client import CodingPlanClient, CodingPlanAPIError
from codex_proxy.config import CodingPlanConfig


@pytest.fixture
def client():
    """Create a test client instance."""
    config = CodingPlanConfig(
        base_url="https://api.test.com/v1",
        api_key="test-key",
        model="test-model",
        timeout=30,
    )
    return CodingPlanClient(config)


class TestCodingPlanClient:
    """Tests for CodingPlanClient."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_chat_non_streaming(self, client):
        """Test non-streaming chat request."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "choices": [{"message": {"content": "Hello!"}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
                },
            )
        )

        result = await client.chat({"model": "test", "messages": [{"role": "user", "content": "Hi"}]})

        assert result["id"] == "chatcmpl-test"
        assert result["choices"][0]["message"]["content"] == "Hello!"

    @respx.mock
    @pytest.mark.asyncio
    async def test_chat_with_api_key_header(self, client):
        """Test that API key is sent in header."""
        route = respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(200, json={"id": "test"})
        )

        await client.chat({"model": "test", "messages": []})

        assert route.calls.last.request.headers["Authorization"] == "Bearer test-key"

    @respx.mock
    @pytest.mark.asyncio
    async def test_chat_streaming(self, client):
        """Test streaming chat request."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                content=b'data: {"choices": [{"delta": {"content": "Hi"}}]}\n\ndata: [DONE]\n\n',
                headers={"content-type": "text/event-stream"},
            )
        )

        events = []
        async for event in await client.chat(
            {"model": "test", "messages": [], "stream": True},
            stream=True,
        ):
            events.append(event)

        assert len(events) == 2
        assert events[0] == {"choices": [{"delta": {"content": "Hi"}}]}
        assert events[1] == {"done": True}

    @respx.mock
    @pytest.mark.asyncio
    async def test_chat_error_passthrough(self, client):
        """Test that API errors are raised."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                401,
                json={"error": {"message": "Invalid API key", "type": "authentication_error"}},
            )
        )

        with pytest.raises(CodingPlanAPIError) as exc_info:
            await client.chat({"model": "test", "messages": []})

        assert exc_info.value.status_code == 401

    @respx.mock
    @pytest.mark.asyncio
    async def test_chat_content_type_header(self, client):
        """Test that Content-Type header is set."""
        route = respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(200, json={"id": "test"})
        )

        await client.chat({"model": "test", "messages": []})

        assert route.calls.last.request.headers["Content-Type"] == "application/json"

    @respx.mock
    @pytest.mark.asyncio
    async def test_client_close(self, client):
        """Test that client can be closed."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(200, json={"id": "test"})
        )

        # Make a request first
        await client.chat({"model": "test", "messages": []})

        # Close the client
        await client.close()

        # Make another request - should create a new client
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(200, json={"id": "test2"})
        )

        result = await client.chat({"model": "test", "messages": []})
        assert result["id"] == "test2"

    @respx.mock
    @pytest.mark.asyncio
    async def test_streaming_error(self, client):
        """Test error handling during streaming."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                500,
                json={"error": {"message": "Internal server error", "type": "server_error"}},
            )
        )

        with pytest.raises(CodingPlanAPIError) as exc_info:
            async for _ in await client.chat(
                {"model": "test", "messages": [], "stream": True},
                stream=True,
            ):
                pass

        assert exc_info.value.status_code == 500

    @respx.mock
    @pytest.mark.asyncio
    async def test_multiple_streaming_events(self, client):
        """Test multiple events in a stream."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                content=(
                    b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
                    b'data: {"choices": [{"delta": {"content": " world"}}]}\n\n'
                    b'data: {"choices": [{"delta": {"content": "!"}}]}\n\n'
                    b'data: [DONE]\n\n'
                ),
                headers={"content-type": "text/event-stream"},
            )
        )

        events = []
        async for event in await client.chat(
            {"model": "test", "messages": [], "stream": True},
            stream=True,
        ):
            events.append(event)

        assert len(events) == 4
        assert events[0]["choices"][0]["delta"]["content"] == "Hello"
        assert events[1]["choices"][0]["delta"]["content"] == " world"
        assert events[2]["choices"][0]["delta"]["content"] == "!"
        assert events[3] == {"done": True}

    @respx.mock
    @pytest.mark.asyncio
    async def test_base_url_trailing_slash(self):
        """Test that trailing slash in base_url is handled."""
        config = CodingPlanConfig(
            base_url="https://api.test.com/v1/",  # With trailing slash
            api_key="test-key",
            model="test-model",
            timeout=30,
        )
        client = CodingPlanClient(config)

        route = respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(200, json={"id": "test"})
        )

        await client.chat({"model": "test", "messages": []})

        # Should still work correctly
        assert route.calls.last.request.url == "https://api.test.com/v1/chat/completions"

    @respx.mock
    @pytest.mark.asyncio
    async def test_error_data_preserved(self, client):
        """Test that error data is preserved in exception."""
        respx.post("https://api.test.com/v1/chat/completions").mock(
            return_value=Response(
                400,
                json={
                    "error": {
                        "message": "Invalid request",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key"
                    }
                },
            )
        )

        with pytest.raises(CodingPlanAPIError) as exc_info:
            await client.chat({"model": "test", "messages": []})

        assert exc_info.value.status_code == 400
        assert exc_info.value.error_data["error"]["type"] == "invalid_request_error"
        assert exc_info.value.error_data["error"]["code"] == "invalid_api_key"