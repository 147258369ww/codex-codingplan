# Logging Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement split logging so the terminal shows compact human-readable request summaries while the rotating file log retains detailed diagnostic events for debugging.

**Architecture:** Add a small `logging_utils` module for request IDs, formatting, truncation, and color decisions; extend config so console and file logging can be controlled separately; configure a dedicated console summary logger alongside the existing rotating file logger; then refactor request handling and upstream client logging to emit semantic lifecycle events with a shared `request_id`.

**Tech Stack:** Python 3.10+, FastAPI, standard-library logging, pytest, respx, httpx

---

### Task 1: Add logging config defaults and logging utility helpers

**Files:**
- Create: `codex_proxy/logging_utils.py`
- Create: `tests/test_logging_utils.py`
- Modify: `codex_proxy/config.py`
- Modify: `tests/test_config.py`
- Modify: `config.example.yaml`
- Modify: `README.md`

- [ ] **Step 1: Write the failing config and utility tests**

```python
# tests/test_config.py
def test_config_with_logging_defaults(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("""
server:
  host: "0.0.0.0"
  port: 9000

coding_plan:
  base_url: "https://api.example.com/v1"
  api_key: "test-key"
  model: "test-model"
  timeout: 120
""")

    config = Config.load(str(config_file))

    assert config.logging.console_level == "INFO"
    assert config.logging.file_level == "DEBUG"
    assert config.logging.payload_max_chars == 4000
```

```python
# tests/test_logging_utils.py
import io
import re

from codex_proxy.logging_utils import (
    format_bytes,
    format_duration,
    generate_request_id,
    should_use_color,
    truncate_text,
)


def test_generate_request_id_has_expected_shape():
    request_id = generate_request_id()

    assert re.fullmatch(r"req_[0-9a-f]{4}", request_id)


def test_truncate_text_marks_truncated_values():
    truncated, was_truncated = truncate_text("x" * 25, limit=10)

    assert was_truncated is True
    assert truncated == "xxxxxxxxxx...<truncated>"


def test_format_helpers_return_compact_values():
    assert format_bytes(684) == "684B"
    assert format_bytes(1536) == "1.5KB"
    assert format_duration(2.31) == "2.31s"


def test_should_use_color_respects_tty():
    class FakeStream(io.StringIO):
        def isatty(self):
            return True

    assert should_use_color(FakeStream()) is True
    assert should_use_color(io.StringIO()) is False
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run: `pytest tests/test_config.py::test_config_with_logging_defaults tests/test_logging_utils.py -v`
Expected: FAIL because `LoggingConfig` does not define `console_level`, `file_level`, or `payload_max_chars`, and `codex_proxy.logging_utils` does not exist yet.

- [ ] **Step 3: Add the minimal config fields and helper module**

```python
# codex_proxy/config.py
@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    console_level: str = "INFO"
    file_level: str = "DEBUG"
    payload_max_chars: int = 4000
```

```python
# codex_proxy/logging_utils.py
"""Utilities for concise console logging and detailed file logging."""

from __future__ import annotations

import io
import os
import uuid


def generate_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:4]}"


def truncate_text(value: str, limit: int) -> tuple[str, bool]:
    if len(value) <= limit:
        return value, False
    return value[:limit] + "...<truncated>", True


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size}B"
    return f"{size / 1024:.1f}KB"


def format_duration(seconds: float) -> str:
    return f"{seconds:.2f}s"


def should_use_color(stream: io.TextIOBase) -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return bool(getattr(stream, "isatty", lambda: False)())
```

```yaml
# config.example.yaml
logging:
  level: "INFO"
  console_level: "INFO"
  file_level: "DEBUG"
  payload_max_chars: 4000
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

```markdown
# README.md
| `logging` | `console_level` | Console summary log level | `INFO` |
| `logging` | `file_level` | File diagnostic log level | `DEBUG` |
| `logging` | `payload_max_chars` | Maximum payload chars before truncation | `4000` |
```

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run: `pytest tests/test_config.py::test_config_with_logging_defaults tests/test_logging_utils.py -v`
Expected: PASS with the new logging defaults and utility helpers in place.

- [ ] **Step 5: Commit**

```bash
git add codex_proxy/config.py codex_proxy/logging_utils.py tests/test_config.py tests/test_logging_utils.py config.example.yaml README.md
git commit -m "feat: add logging config and helper utilities"
```

### Task 2: Split console summary logging from rotating file logging

**Files:**
- Modify: `codex_proxy/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the failing logging setup tests**

```python
# tests/test_main.py
import io
import logging
from logging.handlers import TimedRotatingFileHandler

from codex_proxy.main import configure_logging


def test_configure_logging_separates_console_and_file_handlers(tmp_path):
    config = Config(
        server=ServerConfig(host="127.0.0.1", port=8080),
        coding_plan=CodingPlanConfig(
            base_url="https://api.test.com/v1",
            api_key="test-key",
            model="test-model",
            timeout=30,
        ),
        logging=LoggingConfig(),
    )

    stream = io.StringIO()
    configure_logging(config, log_dir=tmp_path, console_stream=stream)

    root_logger = logging.getLogger()
    console_logger = logging.getLogger("codex_proxy.console")

    assert any(isinstance(handler, TimedRotatingFileHandler) for handler in root_logger.handlers)
    assert any(isinstance(handler, logging.StreamHandler) for handler in console_logger.handlers)
    assert console_logger.propagate is False


def test_configure_logging_writes_console_summary_to_console_logger_only(tmp_path):
    config = Config(
        server=ServerConfig(host="127.0.0.1", port=8080),
        coding_plan=CodingPlanConfig(
            base_url="https://api.test.com/v1",
            api_key="test-key",
            model="test-model",
            timeout=30,
        ),
        logging=LoggingConfig(),
    )

    stream = io.StringIO()
    configure_logging(config, log_dir=tmp_path, console_stream=stream)

    console_logger = logging.getLogger("codex_proxy.console")
    console_logger.info("done  status=200", extra={"request_id": "req_test"})

    output = stream.getvalue()
    assert "req_test" in output
    assert "done  status=200" in output
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run: `pytest tests/test_main.py::test_configure_logging_separates_console_and_file_handlers tests/test_main.py::test_configure_logging_writes_console_summary_to_console_logger_only -v`
Expected: FAIL because `configure_logging` does not exist and the app still configures both sinks through the root logger.

- [ ] **Step 3: Implement handler separation and console formatting**

```python
# codex_proxy/main.py
def configure_logging(
    config: Config,
    log_dir: Path | None = None,
    console_stream=None,
) -> None:
    log_dir = log_dir or Path(__file__).parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.DEBUG)

    file_handler = TimedRotatingFileHandler(
        log_dir / "codex-proxy.log",
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(getattr(logging, config.logging.file_level.upper()))
    file_handler.setFormatter(logging.Formatter(config.logging.format))
    root_logger.addHandler(file_handler)

    console_logger = logging.getLogger("codex_proxy.console")
    console_logger.handlers.clear()
    console_logger.setLevel(getattr(logging, config.logging.console_level.upper()))
    console_logger.propagate = False

    console_handler = logging.StreamHandler(console_stream)
    console_handler.setLevel(getattr(logging, config.logging.console_level.upper()))
    console_handler.setFormatter(ConsoleFormatter(use_color=should_use_color(console_handler.stream)))
    console_logger.addHandler(console_handler)
```

```python
# codex_proxy/logging_utils.py
import logging
from datetime import datetime


class ConsoleFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "INFO": "\033[36m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
    }
    RESET = "\033[0m"

    def __init__(self, use_color: bool) -> None:
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        level = f"{record.levelname:<5}"
        if self.use_color and record.levelname in self.LEVEL_COLORS:
            level = f"{self.LEVEL_COLORS[record.levelname]}{level}{self.RESET}"
        request_id = getattr(record, "request_id", "-")
        return f"{timestamp}  {level}  {request_id:<8}  {record.getMessage()}"
```

```python
# codex_proxy/main.py
def run():
    config = Config.load("config.yaml")
    configure_logging(config)
    app = create_app(config)
    uvicorn.run(app, host=config.server.host, port=config.server.port)
```

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run: `pytest tests/test_main.py::test_configure_logging_separates_console_and_file_handlers tests/test_main.py::test_configure_logging_writes_console_summary_to_console_logger_only -v`
Expected: PASS with separate file and console logging behavior.

- [ ] **Step 5: Commit**

```bash
git add codex_proxy/main.py codex_proxy/logging_utils.py tests/test_main.py
git commit -m "feat: split console and file logging handlers"
```

### Task 3: Emit semantic request lifecycle logs with shared request IDs

**Files:**
- Modify: `codex_proxy/main.py`
- Modify: `codex_proxy/router.py`
- Modify: `codex_proxy/client.py`
- Modify: `tests/test_router.py`

- [ ] **Step 1: Write the failing request lifecycle logging tests**

```python
# tests/test_router.py
import logging


@respx.mock
def test_non_streaming_request_logs_started_and_done(client, caplog):
    respx.post("https://api.test.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "id": "chatcmpl-test",
                "model": "test-model",
                "choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )
    )

    with caplog.at_level(logging.INFO, logger="codex_proxy.console"):
        response = client.post("/v1/responses", json={"model": "gpt-5", "input": "Hi"})

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records if record.name == "codex_proxy.console"]
    assert any("POST /v1/responses" in message and "model=gpt-5 -> gpt-5" in message for message in messages)
    assert any("done  status=200" in message and "text=6B" in message for message in messages)
    assert all(getattr(record, "request_id", "").startswith("req_") for record in caplog.records if record.name == "codex_proxy.console")


@respx.mock
def test_streaming_tool_call_logs_summary_event(client, caplog):
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

    with caplog.at_level(logging.INFO, logger="codex_proxy.console"):
        response = client.post("/v1/responses", json={"model": "gpt-5", "input": "Weather?", "stream": True})

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records if record.name == "codex_proxy.console"]
    assert any("tool_call" in message and "name=get_weather" in message for message in messages)


@respx.mock
def test_api_error_logs_upstream_error_summary(client, caplog):
    respx.post("https://api.test.com/v1/chat/completions").mock(
        return_value=Response(
            401,
            json={"error": {"type": "invalid_request_error", "message": "Invalid API key"}},
        )
    )

    with caplog.at_level(logging.WARNING, logger="codex_proxy.console"):
        response = client.post("/v1/responses", json={"model": "gpt-5", "input": "Hi"})

    assert response.status_code == 401
    messages = [record.getMessage() for record in caplog.records if record.name == "codex_proxy.console"]
    assert any("upstream_error" in message and "status=401" in message for message in messages)
```

- [ ] **Step 2: Run the targeted tests and verify they fail**

Run: `pytest tests/test_router.py::TestRouter::test_responses_endpoint_non_streaming tests/test_router.py::test_non_streaming_request_logs_started_and_done tests/test_router.py::test_streaming_tool_call_logs_summary_event tests/test_router.py::test_api_error_logs_upstream_error_summary -v`
Expected: FAIL because requests do not yet carry a shared `request_id`, summary logs are not emitted through `codex_proxy.console`, and error and tool-call events are still logged as free-form payload dumps.

- [ ] **Step 3: Implement request-scoped semantic logging in middleware, router, and client**

```python
# codex_proxy/main.py
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = generate_request_id()
        request.state.started_at = time.perf_counter()
        return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", generate_request_id())
    console_logger.error(
        'validation_failed  status=422  message="Request validation failed"',
        extra={"request_id": request_id},
    )
    logger.error(
        "validation.error request_id=%s errors=%s body=%s",
        request_id,
        json.dumps(exc.errors(), ensure_ascii=False),
        (await request.body()).decode("utf-8", errors="replace"),
    )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})
```

```python
# codex_proxy/router.py
console_logger = logging.getLogger("codex_proxy.console")


@app.post("/v1/responses")
async def create_response(http_request: Request, request: ResponsesRequest):
    request_id = http_request.state.request_id
    started_at = http_request.state.started_at
    actual_model = config.coding_plan.resolve_model(request.model)

    console_logger.info(
        "POST /v1/responses  model=%s -> %s  stream=%s  input=%s  tools=%s",
        request.model,
        actual_model,
        request.stream,
        "1msg" if isinstance(request.input, str) else f"{len(request.input)}msg",
        len(request.tools or []),
        extra={"request_id": request_id},
    )
    logger.info(
        "request.started request_id=%s model_requested=%s model_resolved=%s stream=%s",
        request_id,
        request.model,
        actual_model,
        request.stream,
    )

    chat_request = converter.to_chat_completions_request(request, actual_model)
    payload_text = json.dumps(chat_request, ensure_ascii=False)
    payload_excerpt, truncated = truncate_text(payload_text, config.logging.payload_max_chars)
    logger.debug(
        "request.payload request_id=%s truncated=%s payload=%s",
        request_id,
        truncated,
        payload_excerpt,
    )

    if request.stream:
        return StreamingResponse(
            _stream_response(
                client,
                converter,
                chat_request,
                actual_model,
                request_id=request_id,
                started_at=started_at,
                payload_max_chars=config.logging.payload_max_chars,
            ),
            media_type="text/event-stream",
        )

    chat_response = await client.chat(chat_request, request_id=request_id, payload_max_chars=config.logging.payload_max_chars)
    response_payload = converter.to_responses_response(chat_response)
    text_size = len(response_payload["output_text"].encode("utf-8"))
    latency = time.perf_counter() - started_at
    console_logger.info(
        "done  status=200  latency=%s  text=%s  tools=%s  finish=%s",
        format_duration(latency),
        format_bytes(text_size),
        len([item for item in response_payload["output"] if item["type"] == "function_call"]),
        chat_response.get("choices", [{}])[0].get("finish_reason", "unknown"),
        extra={"request_id": request_id},
    )
    logger.info(
        "request.completed request_id=%s status=200 latency_ms=%s output_text_chars=%s",
        request_id,
        int(latency * 1000),
        len(response_payload["output_text"]),
    )
    return response_payload
```

```python
# codex_proxy/router.py
async def _stream_response(
    client: CodingPlanClient,
    converter: Converter,
    chat_request: dict[str, Any],
    model: str,
    request_id: str,
    started_at: float,
    payload_max_chars: int,
):
    ...
    stream = await client.chat(
        chat_request,
        stream=True,
        request_id=request_id,
        payload_max_chars=payload_max_chars,
    )
    ...
    for tool_call in tool_calls:
        state = get_or_create_tool_call_state(tool_call_states, tool_call)
        if not state.added_sent:
            console_logger.info(
                "tool_call  name=%s  call_id=%s  args=%s",
                state.name,
                state.call_id,
                format_bytes(len(state.arguments.encode("utf-8"))),
                extra={"request_id": request_id},
            )
    ...
    if event.get("done"):
        latency = time.perf_counter() - started_at
        console_logger.info(
            "done  status=200  latency=%s  text=%s  tools=%s  finish=stream_done",
            format_duration(latency),
            format_bytes(len(full_content.encode(\"utf-8\"))),
            len(tool_call_states),
            extra={"request_id": request_id},
        )
```

```python
# codex_proxy/client.py
async def chat(
    self,
    request: dict[str, Any],
    stream: bool = False,
    request_id: str | None = None,
    payload_max_chars: int = 4000,
) -> dict[str, Any] | AsyncGenerator[dict[str, Any], None]:
    payload_text = json.dumps(request, ensure_ascii=False)
    payload_excerpt, truncated = truncate_text(payload_text, payload_max_chars)
    logger.debug(
        "upstream.request request_id=%s stream=%s truncated=%s payload=%s",
        request_id,
        stream,
        truncated,
        payload_excerpt,
    )
```

```python
# codex_proxy/client.py
if response.status_code >= 400:
    logger.warning(
        "upstream.error request_id=%s status=%s payload=%s",
        request_id,
        response.status_code,
        json.dumps(error_data, ensure_ascii=False),
    )
    raise CodingPlanAPIError(response.status_code, error_data)
```

```python
# codex_proxy/router.py
except CodingPlanAPIError as e:
    console_logger.warning(
        'upstream_error  status=%s  type=%s  message="%s"',
        e.status_code,
        error_type or "api_error",
        error_message or "An API error occurred",
        extra={"request_id": request_id},
    )
    logger.warning(
        "request.upstream_error request_id=%s status=%s payload=%s",
        request_id,
        e.status_code,
        json.dumps(error_data, ensure_ascii=False),
    )
```

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run: `pytest tests/test_router.py::TestRouter::test_responses_endpoint_non_streaming tests/test_router.py::test_non_streaming_request_logs_started_and_done tests/test_router.py::test_streaming_tool_call_logs_summary_event tests/test_router.py::test_api_error_logs_upstream_error_summary -v`
Expected: PASS with request-scoped summary logs in the console logger and detailed diagnostics retained for file logging.

- [ ] **Step 5: Run the broader regression suite**

Run: `pytest tests/test_main.py tests/test_router.py tests/test_config.py tests/test_logging_utils.py -v`
Expected: PASS with no regressions in app setup, routing, or configuration behavior.

- [ ] **Step 6: Commit**

```bash
git add codex_proxy/main.py codex_proxy/router.py codex_proxy/client.py tests/test_router.py tests/test_main.py tests/test_config.py tests/test_logging_utils.py
git commit -m "feat: add request-scoped summary and diagnostic logging"
```

### Task 4: Manual verification of console and file logging behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a short logging behavior note to the README**

```markdown
## Logging

The proxy writes two kinds of logs:

- Console logs: compact request summaries intended for local development
- File logs: detailed diagnostic entries in `logs/codex-proxy.log`

Use the shared `request_id` from the console to find full request details in the file log.
```

- [ ] **Step 2: Run the full automated test suite**

Run: `pytest tests/ -v`
Expected: PASS across config, converter, router, main, and logging utility coverage.

- [ ] **Step 3: Run the proxy locally**

Run: `python -m codex_proxy.main`
Expected: server starts successfully and writes only concise startup output to the terminal.

- [ ] **Step 4: Send a non-streaming request**

Run:

```bash
curl -s http://127.0.0.1:8080/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-5","input":"Say hello"}'
```

Expected: terminal shows a start line and a done line with a shared `request_id`; `logs/codex-proxy.log` contains a detailed payload and completion entry for the same `request_id`.

- [ ] **Step 5: Send a streaming request with a mocked or real tool call path**

Run:

```bash
curl -N http://127.0.0.1:8080/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"model":"gpt-5","input":"Weather?","stream":true}'
```

Expected: terminal shows a start line, at least one `tool_call` or streaming summary line when applicable, and a final done line; the file log preserves the detailed streaming events without flooding the terminal.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: document split console and file logging"
```
