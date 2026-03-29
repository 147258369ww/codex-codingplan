# codex-proxy/tests/test_models.py
import pytest
from pydantic import ValidationError
from codex_proxy.models import (
    FunctionCallItem,
    Message,
    ResponseFunctionCallItem,
    ResponsesRequest,
    ResponsesResponse,
    OutputContent,
    OutputMessage,
    Usage,
    StreamDeltaEvent,
    StreamDoneEvent,
    StreamCompletedEvent,
    ErrorResponse,
)


class TestMessage:
    def test_message_creation(self):
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_message_invalid_role(self):
        with pytest.raises(ValueError):
            Message(role="invalid", content="test")


class TestResponsesRequest:
    def test_request_with_string_input(self):
        req = ResponsesRequest(model="gpt-5", input="Hello")
        assert req.input == "Hello"
        assert req.stream is False

    def test_request_with_message_list(self):
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hi"},
        ]
        req = ResponsesRequest(model="gpt-5", input=messages)
        assert isinstance(req.input, list)
        assert len(req.input) == 2

    def test_request_default_values(self):
        req = ResponsesRequest(model="gpt-5", input="test")
        assert req.instructions is None
        assert req.tools is None
        assert req.stream is False
        assert req.temperature is None
        assert req.top_p is None

    def test_request_accepts_function_call_output_items(self):
        req = ResponsesRequest(
            model="gpt-5",
            input=[
                {"type": "message", "role": "user", "content": "Check weather"},
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": {"temperature": 26},
                },
            ],
        )

        assert len(req.input) == 2
        assert req.input[1].type == "function_call_output"
        assert req.input[1].call_id == "call_123"
        assert req.input[1].output == {"temperature": 26}

    def test_request_accepts_function_call_items(self):
        req = ResponsesRequest(
            model="gpt-5",
            input=[
                {
                    "type": "function_call",
                    "call_id": "call_456",
                    "name": "get_weather",
                    "arguments": '{"city":"Berlin"}',
                }
            ],
        )

        assert len(req.input) == 1
        assert req.input[0].type == "function_call"
        assert req.input[0].name == "get_weather"
        assert isinstance(req.input[0], FunctionCallItem)

    def test_request_accepts_tool_choice_and_parallel_tool_calls(self):
        req = ResponsesRequest(
            model="gpt-5",
            input="Hello",
            tool_choice="auto",
            parallel_tool_calls=True,
        )

        assert req.tool_choice == "auto"
        assert req.parallel_tool_calls is True

    def test_request_rejects_malformed_typed_items(self):
        with pytest.raises(ValidationError):
            ResponsesRequest(
                model="gpt-5",
                input=[
                    {"type": "mesage", "role": "user", "content": "x"},
                ],
            )


class TestResponsesResponse:
    def test_response_creation(self):
        response = ResponsesResponse(
            id="resp_123",
            created_at=1741369938.0,
            status="completed",
            model="gpt-5",
            output=[
                OutputMessage(
                    id="msg_123",
                    type="message",
                    role="assistant",
                    content=[OutputContent(type="output_text", text="Hello!")],
                )
            ],
            output_text="Hello!",
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )
        assert response.id == "resp_123"
        assert response.output_text == "Hello!"
        assert response.usage.total_tokens == 15

    def test_response_accepts_function_call_output_items(self):
        response = ResponsesResponse(
            id="resp_123",
            created_at=1741369938.0,
            status="completed",
            model="gpt-5",
            output=[
                {
                    "id": "msg_123",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Let me check."}],
                },
                {
                    "id": "fc_123",
                    "type": "function_call",
                    "call_id": "call_123",
                    "name": "get_weather",
                    "arguments": "{\"city\":\"Hangzhou\"}",
                },
            ],
            output_text="Let me check.",
            usage=Usage(input_tokens=10, output_tokens=4, total_tokens=14),
        )

        assert len(response.output) == 2
        assert response.output[0].type == "message"
        assert response.output[1].type == "function_call"
        assert isinstance(response.output[1], ResponseFunctionCallItem)
        assert response.output[1].id == "fc_123"
        assert response.output[1].call_id == "call_123"
        assert response.output[1].arguments == "{\"city\":\"Hangzhou\"}"


class TestStreamDeltaEvent:
    def test_delta_event_creation(self):
        event = StreamDeltaEvent(delta="Hello")
        assert event.type == "response.output_text.delta"
        assert event.delta == "Hello"
        assert event.output_index == 0

    def test_delta_event_with_custom_output_index(self):
        event = StreamDeltaEvent(delta="World", output_index=2)
        assert event.output_index == 2


class TestStreamDoneEvent:
    def test_done_event_creation(self):
        event = StreamDoneEvent()
        assert event.type == "response.output_text.done"
        assert event.output_index == 0

    def test_done_event_with_custom_output_index(self):
        event = StreamDoneEvent(output_index=1)
        assert event.output_index == 1


class TestStreamCompletedEvent:
    def test_completed_event_creation(self):
        response = ResponsesResponse(
            id="resp_456",
            created_at=1741369938.0,
            status="completed",
            model="gpt-5",
            output=[
                OutputMessage(
                    id="msg_456",
                    type="message",
                    role="assistant",
                    content=[OutputContent(type="output_text", text="Done!")],
                )
            ],
            output_text="Done!",
            usage=Usage(input_tokens=5, output_tokens=3, total_tokens=8),
        )
        event = StreamCompletedEvent(response=response)
        assert event.type == "response.completed"
        assert event.response.id == "resp_456"
        assert event.response.status == "completed"


class TestErrorResponse:
    def test_error_response_creation(self):
        error = ErrorResponse(error={"message": "Something went wrong", "type": "invalid_request_error"})
        assert error.error["message"] == "Something went wrong"
        assert error.error["type"] == "invalid_request_error"

    def test_error_response_serialization(self):
        error = ErrorResponse(error={"message": "Rate limit exceeded", "type": "rate_limit_error"})
        json_data = error.model_dump()
        assert "error" in json_data
        assert json_data["error"]["message"] == "Rate limit exceeded"
