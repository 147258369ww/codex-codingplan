"""Tests for converter module."""

import pytest
from codex_proxy.converter import Converter
from codex_proxy.models import ResponsesRequest, Message


class TestConverterRequestConversion:
    def setup_method(self):
        self.converter = Converter()

    def test_convert_simple_string_input(self):
        """Convert string input to messages array."""
        req = ResponsesRequest(model="gpt-5", input="Hello")
        result = self.converter.to_chat_completions_request(req, "default-model")

        assert result["model"] == "gpt-5"
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][0]["content"] == "Hello"

    def test_convert_with_instructions(self):
        """Convert with instructions -> system message first."""
        req = ResponsesRequest(
            model="gpt-5",
            input="Hello",
            instructions="You are helpful"
        )
        result = self.converter.to_chat_completions_request(req, "default-model")

        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "system"
        assert result["messages"][0]["content"] == "You are helpful"
        assert result["messages"][1]["role"] == "user"

    def test_convert_message_list_input(self):
        """Convert message list input directly."""
        req = ResponsesRequest(
            model="gpt-5",
            input=[
                Message(role="user", content="Hi"),
                Message(role="assistant", content="Hello!"),
                Message(role="user", content="How are you?"),
            ]
        )
        result = self.converter.to_chat_completions_request(req, "default-model")

        assert len(result["messages"]) == 3
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"

    def test_convert_uses_default_model_when_not_specified(self):
        """Use default model when request model is empty."""
        req = ResponsesRequest(model="", input="test")
        result = self.converter.to_chat_completions_request(req, "qwen-coder-plus")

        assert result["model"] == "qwen-coder-plus"

    def test_convert_max_output_tokens_to_max_tokens(self):
        """Convert max_output_tokens to max_tokens."""
        req = ResponsesRequest(model="gpt-5", input="test", max_output_tokens=1000)
        result = self.converter.to_chat_completions_request(req, "default")

        assert result["max_tokens"] == 1000

    def test_convert_excludes_none_values(self):
        """Exclude None values from the request."""
        req = ResponsesRequest(model="gpt-5", input="test")
        result = self.converter.to_chat_completions_request(req, "default")

        assert "instructions" not in result
        assert "tools" not in result
        assert "max_tokens" not in result


class TestConverterResponseConversion:
    def setup_method(self):
        self.converter = Converter()

    def test_convert_response(self):
        """Convert Chat Completions response to Responses format."""
        chat_response = {
            "id": "chatcmpl-abc123",
            "object": "chat.completion",
            "created": 1741369938,
            "model": "qwen-coder-plus",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Hello, how can I help you?",
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 8,
                "total_tokens": 18,
            },
        }

        result = self.converter.to_responses_response(chat_response)

        assert result["id"].startswith("resp_")
        assert result["object"] == "response"
        assert result["status"] == "completed"
        assert result["model"] == "qwen-coder-plus"
        assert result["output_text"] == "Hello, how can I help you?"
        assert len(result["output"]) == 1
        assert result["output"][0]["content"][0]["text"] == "Hello, how can I help you?"
        assert result["usage"]["input_tokens"] == 10
        assert result["usage"]["output_tokens"] == 8

    def test_convert_response_id_generation(self):
        """Generate response ID from chat completion ID."""
        chat_response = {
            "id": "chatcmpl-xyz789",
            "choices": [{"message": {"content": "test"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

        result = self.converter.to_responses_response(chat_response)

        # Should convert chatcmpl-xyz789 -> resp_xyz789
        assert "xyz789" in result["id"]


class TestConverterStreamEvent:
    def setup_method(self):
        self.converter = Converter()

    def test_convert_content_delta_event(self):
        """Convert Chat Completions delta event to Responses format."""
        chat_event = {
            "id": "chatcmpl-test",
            "object": "chat.completion.chunk",
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "Hello"},
                    "finish_reason": None,
                }
            ],
        }

        result = self.converter.to_responses_stream_event(
            chat_event, "resp_test", "gpt-5"
        )

        assert result is not None
        assert result["type"] == "response.output_text.delta"
        assert result["delta"] == "Hello"
        assert result["output_index"] == 0

    def test_convert_role_event_returns_none(self):
        """Role-only events should be skipped (return None)."""
        chat_event = {
            "id": "chatcmpl-test",
            "choices": [{"delta": {"role": "assistant"}, "finish_reason": None}],
        }

        result = self.converter.to_responses_stream_event(
            chat_event, "resp_test", "gpt-5"
        )

        assert result is None

    def test_convert_finish_event(self):
        """Convert finish event to done event."""
        chat_event = {
            "id": "chatcmpl-test",
            "choices": [{"delta": {}, "finish_reason": "stop"}],
        }

        result = self.converter.to_responses_stream_event(
            chat_event, "resp_test", "gpt-5"
        )

        assert result is not None
        assert result["type"] == "response.output_text.done"

    def test_convert_empty_delta_returns_none(self):
        """Empty delta without finish_reason should return None."""
        chat_event = {
            "id": "chatcmpl-test",
            "choices": [{"delta": {}, "finish_reason": None}],
        }

        result = self.converter.to_responses_stream_event(
            chat_event, "resp_test", "gpt-5"
        )

        assert result is None

    def test_create_completed_event(self):
        """Test creating response.completed event."""
        result = self.converter.create_completed_event(
            response_id="resp_test123",
            model="gpt-5",
            full_content="Hello world",
            usage={"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        )

        assert result["type"] == "response.completed"
        assert result["response"]["id"] == "resp_test123"
        assert result["response"]["model"] == "gpt-5"
        assert result["response"]["output_text"] == "Hello world"
        assert result["response"]["usage"]["input_tokens"] == 5
        assert result["response"]["usage"]["output_tokens"] == 2