"""Pydantic models for Responses API request/response."""

from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class InputTextContent(BaseModel):
    """Input text content item."""

    type: Literal["input_text"] = "input_text"
    text: str


class InputImageContent(BaseModel):
    """Input image content item."""

    type: Literal["input_image"]
    image_url: str


class InputRefusalContent(BaseModel):
    """Input refusal content item."""

    type: Literal["refusal"]
    refusal: str


class OutputTextContent(BaseModel):
    """Output text content item (for history messages)."""

    type: Literal["output_text"] = "output_text"
    text: str


InputContent = Union[InputTextContent, InputImageContent, InputRefusalContent, OutputTextContent, str]


class InputMessage(BaseModel):
    """Input message in Responses API format."""

    type: Literal["message"] = "message"
    role: Literal["system", "user", "assistant", "developer", "tool"]
    content: Union[str, list[InputContent]]


class FunctionCallItem(BaseModel):
    """Function call item in Responses API format."""

    type: Literal["function_call"] = "function_call"
    call_id: str
    name: str
    arguments: str


class FunctionCallOutputItem(BaseModel):
    """Function call output item in Responses API format."""

    type: Literal["function_call_output"] = "function_call_output"
    call_id: str
    output: Any


# Legacy Message for backwards compatibility
class Message(BaseModel):
    """Chat message (legacy format)."""

    role: Literal["system", "user", "assistant", "developer", "tool"]
    content: Union[str, list[InputContent]]

    model_config = ConfigDict(extra="forbid")


RequestInputItem = Union[InputMessage, Message, FunctionCallItem, FunctionCallOutputItem]


class ResponsesRequest(BaseModel):
    """Responses API request model."""

    model: str
    input: Union[str, list[RequestInputItem]]
    instructions: str | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None
    stream: bool = False
    max_output_tokens: int | None = Field(default=None, validation_alias="maxOutputTokens", serialization_alias="maxOutputTokens")
    temperature: float | None = None
    top_p: float | None = None
    previous_response_id: str | None = None
    truncation: str | None = None
    metadata: dict[str, Any] | None = None

    model_config = ConfigDict(populate_by_name=True)


class OutputContent(BaseModel):
    """Output content item."""

    type: Literal["output_text"] = "output_text"
    text: str


class OutputMessage(BaseModel):
    """Output message."""

    id: str
    type: Literal["message"] = "message"
    role: Literal["assistant"] = "assistant"
    content: list[OutputContent]


OutputItem = Union[OutputMessage, FunctionCallItem]


class Usage(BaseModel):
    """Token usage statistics."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


class ResponsesResponse(BaseModel):
    """Responses API response model."""

    id: str
    object: Literal["response"] = "response"
    created_at: float
    status: Literal["completed", "failed", "cancelled"]
    model: str
    output: list[OutputItem]
    output_text: str
    usage: Usage


class StreamDeltaEvent(BaseModel):
    """Streaming delta event."""

    type: Literal["response.output_text.delta"] = "response.output_text.delta"
    delta: str
    output_index: int = 0


class StreamDoneEvent(BaseModel):
    """Streaming done event."""

    type: Literal["response.output_text.done"] = "response.output_text.done"
    output_index: int = 0


class StreamCompletedEvent(BaseModel):
    """Streaming completed event."""

    type: Literal["response.completed"] = "response.completed"
    response: ResponsesResponse


class ErrorResponse(BaseModel):
    """Error response."""

    error: dict[str, str]
