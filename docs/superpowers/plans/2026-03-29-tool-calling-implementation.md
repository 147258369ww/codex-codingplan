# Tool Calling Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Responses-to-Chat tool-calling compatibility so Codex can complete non-streaming and streaming function-call loops through the proxy.

**Architecture:** Extend the request and response models to represent tool-call items, teach the converter to map tool history and tool-call outputs between Responses and Chat formats, and replace the router's text-only streaming assumptions with a small stateful event builder that can emit both text and function-call events. Preserve the existing text-only path and validate every new behavior with targeted tests first.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, pytest, respx, httpx

---

### Task 1: Extend request and response models for tool-calling

**Files:**
- Modify: `codex_proxy/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing model tests**

```python
from codex_proxy.models import ResponsesRequest


class TestResponsesRequest:
    def test_request_accepts_function_call_output_items(self):
        req = ResponsesRequest(
            model="gpt-5",
            input=[
                {"type": "message", "role": "user", "content": "Check weather"},
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": "{\"temperature\": 26}",
                },
            ],
        )

        assert len(req.input) == 2
        assert req.input[1].type == "function_call_output"
        assert req.input[1].call_id == "call_123"

    def test_request_accepts_tool_choice_and_parallel_tool_calls(self):
        req = ResponsesRequest(
            model="gpt-5",
            input="Hello",
            tool_choice="auto",
            parallel_tool_calls=True,
        )

        assert req.tool_choice == "auto"
        assert req.parallel_tool_calls is True
```

- [ ] **Step 2: Run the targeted model tests and verify they fail**

Run: `pytest tests/test_models.py -v`
Expected: FAIL because `ResponsesRequest` does not yet accept `function_call_output`, `tool_choice`, or `parallel_tool_calls`.

- [ ] **Step 3: Add the minimal model support**

```python
class FunctionCallItem(BaseModel):
    type: Literal["function_call"] = "function_call"
    call_id: str
    name: str
    arguments: str


class FunctionCallOutputItem(BaseModel):
    type: Literal["function_call_output"] = "function_call_output"
    call_id: str
    output: str


RequestInputItem = Union[InputMessage, Message, FunctionCallItem, FunctionCallOutputItem]


class ResponsesRequest(BaseModel):
    model: str
    input: Union[str, list[RequestInputItem]]
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None
```

- [ ] **Step 4: Run the model tests and verify they pass**

Run: `pytest tests/test_models.py -v`
Expected: PASS for the new request parsing tests and existing model coverage.

- [ ] **Step 5: Commit**

```bash
git add codex_proxy/models.py tests/test_models.py
git commit -m "feat: add tool-calling request models"
```

### Task 2: Convert Responses tool inputs into Chat request messages

**Files:**
- Modify: `codex_proxy/converter.py`
- Test: `tests/test_converter.py`

- [ ] **Step 1: Write the failing converter request tests**

```python
def test_convert_function_call_output_to_tool_message(self):
    req = ResponsesRequest(
        model="gpt-5",
        input=[
            {"type": "message", "role": "user", "content": "Weather?"},
            {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "{\"temperature\": 26}",
            },
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
        "content": "{\"temperature\": 26}",
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
                "arguments": "{\"city\": \"Shanghai\"}",
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
```

- [ ] **Step 2: Run the converter request tests and verify they fail**

Run: `pytest tests/test_converter.py::TestConverterRequestConversion -v`
Expected: FAIL because tool-call items are not mapped into Chat `assistant.tool_calls` or `tool` messages yet.

- [ ] **Step 3: Implement request-side tool conversion**

```python
def to_chat_completions_request(self, responses_request: ResponsesRequest, resolved_model: str) -> dict[str, Any]:
    request = {
        "model": resolved_model,
        "messages": self._convert_input(responses_request.input, responses_request.instructions),
        "stream": responses_request.stream,
    }

    if responses_request.tool_choice is not None:
        request["tool_choice"] = responses_request.tool_choice
    if responses_request.parallel_tool_calls is not None:
        request["parallel_tool_calls"] = responses_request.parallel_tool_calls
```

```python
def _convert_input(self, input_value: str | list, instructions: str | None) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if instructions:
        messages.append({"role": "system", "content": instructions})

    if isinstance(input_value, str):
        messages.append({"role": "user", "content": input_value})
        return messages

    for item in input_value:
        messages.extend(self._convert_input_item(item))
    return messages


def _convert_input_item(self, item: Any) -> list[dict[str, Any]]:
    data = item.model_dump() if hasattr(item, "model_dump") else item
    if isinstance(data, dict) and data.get("type") == "function_call":
        return [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": data["call_id"],
                "type": "function",
                "function": {"name": data["name"], "arguments": data["arguments"]},
            }],
        }]
    if isinstance(data, dict) and data.get("type") == "function_call_output":
        return [{
            "role": "tool",
            "tool_call_id": data["call_id"],
            "content": data["output"],
        }]
    return [self._convert_message(item)]
```

- [ ] **Step 4: Run the converter request tests and verify they pass**

Run: `pytest tests/test_converter.py::TestConverterRequestConversion -v`
Expected: PASS for tool history, tool outputs, and tool field forwarding.

- [ ] **Step 5: Commit**

```bash
git add codex_proxy/converter.py tests/test_converter.py
git commit -m "feat: convert tool call requests to chat format"
```

### Task 3: Convert Chat tool-call responses into Responses output items

**Files:**
- Modify: `codex_proxy/converter.py`
- Test: `tests/test_converter.py`

- [ ] **Step 1: Write the failing non-streaming response tests**

```python
def test_convert_response_with_tool_calls(self):
    chat_response = {
        "id": "chatcmpl-tool123",
        "model": "qwen3.5-plus",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": "{\"city\":\"Hangzhou\"}",
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
    }

    result = self.converter.to_responses_response(chat_response)

    assert result["output_text"] == ""
    assert result["output"][0]["type"] == "function_call"
    assert result["output"][0]["call_id"] == "call_123"
    assert result["output"][0]["name"] == "get_weather"


def test_convert_response_with_text_and_tool_calls(self):
    chat_response = {
        "id": "chatcmpl-mixed123",
        "model": "qwen3.5-plus",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [{
                    "id": "call_999",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": "{\"city\":\"Suzhou\"}",
                    },
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 6, "total_tokens": 16},
    }

    result = self.converter.to_responses_response(chat_response)

    assert result["output_text"] == "Let me check."
    assert result["output"][0]["type"] == "message"
    assert result["output"][1]["type"] == "function_call"
```

- [ ] **Step 2: Run the response conversion tests and verify they fail**

Run: `pytest tests/test_converter.py::TestConverterResponseConversion -v`
Expected: FAIL because tool calls are currently dropped and every response is forced into a text message.

- [ ] **Step 3: Implement mixed output conversion**

```python
def to_responses_response(self, chat_response: dict[str, Any]) -> dict[str, Any]:
    choice = chat_response.get("choices", [{}])[0] if chat_response.get("choices") else {}
    message = choice.get("message", {})
    content_text = message.get("content") or ""
    tool_calls = message.get("tool_calls") or []

    output_items: list[dict[str, Any]] = []
    if content_text:
        output_items.append(self._build_output_message(content_text))

    for tool_call in tool_calls:
        output_items.append({
            "id": "fc_" + str(uuid.uuid4())[:8],
            "type": "function_call",
            "call_id": tool_call.get("id", ""),
            "name": tool_call.get("function", {}).get("name", ""),
            "arguments": tool_call.get("function", {}).get("arguments", ""),
        })
```

- [ ] **Step 4: Run the response conversion tests and verify they pass**

Run: `pytest tests/test_converter.py::TestConverterResponseConversion -v`
Expected: PASS for text-only responses, tool-call-only responses, and mixed responses.

- [ ] **Step 5: Commit**

```bash
git add codex_proxy/converter.py tests/test_converter.py
git commit -m "feat: convert tool call responses to responses format"
```

### Task 4: Add stream state handling for text and tool-call events

**Files:**
- Modify: `codex_proxy/converter.py`
- Modify: `codex_proxy/router.py`
- Modify: `codex_proxy/tools.py`
- Test: `tests/test_converter.py`
- Test: `tests/test_router.py`

- [ ] **Step 1: Write the failing streaming tests**

```python
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

    response = client.post("/v1/responses", json={"model": "gpt-5", "input": "Weather?", "stream": True})
    content = response.content.decode()

    assert "response.function_call_arguments.delta" in content
    assert "response.function_call_arguments.done" in content
    assert "response.output_item.done" in content
```

```python
def test_convert_stream_event_with_tool_call_delta(self):
    chat_event = {
        "choices": [{
            "delta": {
                "tool_calls": [{
                    "index": 0,
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": "{\"city\":"},
                }]
            },
            "finish_reason": None,
        }]
    }

    result = self.converter.to_responses_stream_event(chat_event, "resp_test", "gpt-5")

    assert result is not None
    assert result["type"] == "response.function_call_arguments.delta"
    assert result["delta"] == "{\"city\":"
```

- [ ] **Step 2: Run the streaming tests and verify they fail**

Run: `pytest tests/test_converter.py::TestConverterStreamEvent tests/test_router.py::TestRouter::test_responses_endpoint_streaming -v`
Expected: FAIL because streaming currently only knows how to emit text events.

- [ ] **Step 3: Implement stream state helpers and router integration**

```python
@dataclass
class ToolCallState:
    index: int
    item_id: str
    call_id: str
    name: str
    arguments: str = ""
    added_sent: bool = False
    done_sent: bool = False
```

```python
def to_responses_stream_event(self, chat_event: dict[str, Any], response_id: str, model: str) -> dict[str, Any] | None:
    choice = (chat_event.get("choices") or [{}])[0]
    delta = choice.get("delta", {})

    tool_calls = delta.get("tool_calls") or []
    if tool_calls:
        tool_call = tool_calls[0]
        arguments = tool_call.get("function", {}).get("arguments")
        if arguments:
            return {
                "type": "response.function_call_arguments.delta",
                "delta": arguments,
                "output_index": tool_call.get("index", 0),
            }
```

```python
if tool_delta_detected and not state.added_sent:
    yield response.output_item.added
if tool_argument_delta:
    yield response.function_call_arguments.delta
if stream_finished:
    yield response.function_call_arguments.done
    yield response.output_item.done
```

- [ ] **Step 4: Run the focused streaming tests and verify they pass**

Run: `pytest tests/test_converter.py::TestConverterStreamEvent tests/test_router.py::TestRouter::test_responses_endpoint_streaming -v`
Expected: PASS for existing text events and new function-call event coverage.

- [ ] **Step 5: Commit**

```bash
git add codex_proxy/converter.py codex_proxy/router.py codex_proxy/tools.py tests/test_converter.py tests/test_router.py
git commit -m "feat: add streaming tool call events"
```

### Task 5: Add regression coverage for mixed text and tool flows

**Files:**
- Modify: `tests/test_converter.py`
- Modify: `tests/test_router.py`

- [ ] **Step 1: Write the failing regression tests**

```python
def test_convert_response_empty_choices_keeps_empty_message(self):
    chat_response = {
        "id": "chatcmpl-empty",
        "choices": [],
        "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1},
    }

    result = self.converter.to_responses_response(chat_response)

    assert result["output"][0]["type"] == "message"
    assert result["output"][0]["content"][0]["text"] == ""
```

```python
@respx.mock
def test_streaming_mixed_text_and_tool_call(self, client):
    respx.post("https://api.test.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            content=(
                b'data: {"id":"chatcmpl-test","choices":[{"delta":{"content":"Let me check."}}]}\n\n'
                b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_123","type":"function","function":{"name":"get_weather","arguments":"{\\"city\\":\\"Hangzhou\\"}"}}]}}]}\n\n'
                b'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
                b'data: [DONE]\n\n'
            ),
            headers={"content-type": "text/event-stream"},
        )
    )

    response = client.post("/v1/responses", json={"model": "gpt-5", "input": "Weather?", "stream": True})
    content = response.content.decode()

    assert "response.output_text.delta" in content
    assert "response.function_call_arguments.done" in content
    assert "response.completed" in content
```

- [ ] **Step 2: Run the regression tests and verify they fail where expected**

Run: `pytest tests/test_converter.py tests/test_router.py -v`
Expected: FAIL only on the new mixed text and tool assertions until implementation is complete.

- [ ] **Step 3: Tighten edge-case handling without changing the happy path**

```python
if not output_items:
    output_items.append(self._build_output_message(""))

for tool_state in sorted(tool_states.values(), key=lambda item: item.index):
    finalize_tool_state(tool_state)
```

- [ ] **Step 4: Run the full targeted suite and verify it passes**

Run: `pytest tests/test_models.py tests/test_converter.py tests/test_router.py -v`
Expected: PASS with all existing coverage preserved and new tool-calling behavior validated.

- [ ] **Step 5: Commit**

```bash
git add tests/test_converter.py tests/test_router.py codex_proxy/converter.py codex_proxy/router.py
git commit -m "test: add tool calling regression coverage"
```

### Task 6: Update docs to match delivered behavior

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write the failing doc expectations as a checklist**

```text
- README must describe function_call/function_call_output support
- README must describe tool_choice/parallel_tool_calls support
- CLAUDE feature status must move tool-calling items from missing to implemented
```

- [ ] **Step 2: Inspect the current docs and confirm the gaps**

Run: `rg -n "Tool calling|tool_choice|parallel_tool_calls|Feature Status|missing features" README.md CLAUDE.md`
Expected: Existing text still describes tool calling as incomplete or omits the new details.

- [ ] **Step 3: Update the docs**

```markdown
## API Format Conversion

- `function_call_output` inputs are converted into Chat `tool` messages
- assistant `tool_calls` are converted back into Responses `function_call` items
- `tool_choice` and `parallel_tool_calls` are forwarded when present
```

```markdown
## Feature Status

- **Tool calling**: implemented for `function_call` output and `function_call_output` input
- **`tool_choice` / `parallel_tool_calls`**: implemented
```

- [ ] **Step 4: Run the targeted test suite again to guard against doc-only drift**

Run: `pytest tests/test_models.py tests/test_converter.py tests/test_router.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: document tool calling support"
```

## Self-Review

### Spec coverage

- Request-side tool history and tool outputs are covered by Task 1 and Task 2.
- Non-streaming tool-call output conversion is covered by Task 3.
- Streaming tool-call event emission is covered by Task 4 and Task 5.
- Error handling is exercised through existing router tests and preserved while adding new cases in Task 4 and Task 5.
- Documentation updates are covered by Task 6.

### Placeholder scan

- No `TODO`, `TBD`, or deferred implementation markers remain.
- Every code-changing task includes a concrete code example.
- Every verification step includes an exact command and expected outcome.

### Type consistency

- Uses `function_call`, `function_call_output`, `tool_choice`, and `parallel_tool_calls` consistently across model, converter, and router tasks.
- Keeps Chat-side names aligned with upstream fields: `tool_calls`, `tool_call_id`, and `function.arguments`.
