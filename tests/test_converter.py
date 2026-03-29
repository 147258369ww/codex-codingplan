"""Tests for converter module."""

import pytest
from codex_proxy.converter import Converter
from codex_proxy.models import ResponsesRequest, Message


class TestConverterRequestConversion:
    def setup_method(self):
        self.converter = Converter()

    def test_convert_simple_string_input(self):
        """Convert string input to messages array, using resolved model."""
        req = ResponsesRequest(model="gpt-5", input="Hello")
        result = self.converter.to_chat_completions_request(req, "qwen3.5-plus")

        # Model should be the resolved_model parameter, not the request's model
        assert result["model"] == "qwen3.5-plus"
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

    def test_convert_tools_parameter(self):
        """Tools parameter should be passed through to the request."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather info",
                    "parameters": {"type": "object"},
                },
            }
        ]
        req = ResponsesRequest(model="gpt-5", input="test", tools=tools)
        result = self.converter.to_chat_completions_request(req, "default")

        assert "tools" in result
        assert result["tools"] == tools

    def test_convert_function_call_output_to_tool_message(self):
        req = ResponsesRequest(
            model="gpt-5",
            input=[
                {"type": "message", "role": "user", "content": "Weather?"},
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": {"temperature": 26},
                },
            ],
            tools=[
                {
                    "type": "function",
                    "name": "get_weather",
                    "parameters": {"type": "object"},
                }
            ],
            tool_choice="auto",
            parallel_tool_calls=True,
        )

        result = self.converter.to_chat_completions_request(req, "default-model")

        assert result["tool_choice"] == "auto"
        assert result["parallel_tool_calls"] is True
        assert result["messages"][1] == {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": '{"temperature": 26}',
        }

    def test_convert_function_call_output_non_json_native_value_is_json_stringified(self):
        class CustomOutput:
            def __str__(self):
                return "custom-output"

        req = ResponsesRequest(
            model="gpt-5",
            input=[
                {"type": "message", "role": "user", "content": "Weather?"},
                {
                    "type": "function_call_output",
                    "call_id": "call_789",
                    "output": CustomOutput(),
                },
            ],
        )

        result = self.converter.to_chat_completions_request(req, "default-model")

        assert result["messages"][1] == {
            "role": "tool",
            "tool_call_id": "call_789",
            "content": '"custom-output"',
        }

    def test_convert_function_call_history_to_assistant_tool_calls(self):
        req = ResponsesRequest(
            model="gpt-5",
            input=[
                {"type": "message", "role": "user", "content": "Weather?"},
                {
                    "type": "function_call",
                    "call_id": "call_456",
                    "name": "get_weather",
                    "arguments": '{"city": "Shanghai"}',
                },
            ],
        )

        result = self.converter.to_chat_completions_request(req, "default-model")

        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][1]["tool_calls"][0]["id"] == "call_456"
        assert result["messages"][1]["tool_calls"][0]["function"]["name"] == "get_weather"

    def test_convert_simplified_function_tools(self):
        req = ResponsesRequest(
            model="gpt-5",
            input="test",
            tools=[
                {
                    "type": "function",
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object"},
                }
            ],
        )

        result = self.converter.to_chat_completions_request(req, "default-model")

        assert result["tools"][0]["function"]["name"] == "get_weather"

    def test_convert_dict_tool_choice_is_forwarded(self):
        req = ResponsesRequest(
            model="gpt-5",
            input="test",
            tools=[
                {
                    "type": "function",
                    "name": "get_weather",
                    "parameters": {"type": "object"},
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "get_weather"},
            },
        )

        result = self.converter.to_chat_completions_request(req, "default-model")

        assert result["tool_choice"] == {
            "type": "function",
            "function": {"name": "get_weather"},
        }

    def test_omit_tool_controls_when_no_valid_tools_remain(self):
        req = ResponsesRequest(
            model="gpt-5",
            input="test",
            tools=[
                {"type": "function"},
                {"type": "web_search"},
            ],
            tool_choice="auto",
            parallel_tool_calls=True,
        )

        result = self.converter.to_chat_completions_request(req, "default-model")

        assert "tools" not in result
        assert "tool_choice" not in result
        assert "parallel_tool_calls" not in result


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

    def test_convert_response_empty_choices(self):
        """Handle empty choices array gracefully."""
        chat_response = {
            "id": "chatcmpl-empty",
            "choices": [],
            "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
        }

        result = self.converter.to_responses_response(chat_response)

        assert result["id"].startswith("resp_")
        assert result["status"] == "completed"
        assert result["output_text"] == ""
        assert len(result["output"]) == 1
        assert result["output"][0]["content"][0]["text"] == ""


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
